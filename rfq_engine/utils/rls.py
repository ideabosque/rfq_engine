# -*- coding: utf-8 -*-
"""Row-Level Security (RLS) helpers for the PostgreSQL backend.

Enforces tenant isolation at the database level so that even if a query
forgets to filter on ``partition_key``, PostgreSQL still restricts rows to the
current tenant context. Only imported when ``DB_BACKEND=postgresql``.

- ``set_rls_context(session, partition_key)`` sets ``SET app.tenant_id`` at the
  start of each request/entry point.
- ``create_rls_policies(engine)`` applies RLS policies to all partition-keyed
  tables (called during table initialization).
"""
from __future__ import print_function

__author__ = "bibow"

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# All RFQ PostgreSQL tables carry a ``partition_key`` column, so every table
# participates in tenant isolation (unprefixed names).
_RLS_TABLES = [
    "items",
    "provider_items",
    "provider_item_batches",
    "segments",
    "segment_contacts",
    "fx_rates",
    "cancellation_policies",
    "bundles",
    "bundle_components",
    "item_catalog_refs",
    "item_price_tiers",
    "discount_prompts",
    "requests",
    "quotes",
    "quote_items",
    "installments",
    "files",
    "availability_holds",
]


def set_rls_context(session: Any, partition_key: str) -> None:
    """Set the RLS tenant context for the current database session.

    Uses connection-level ``SET`` (not ``SET LOCAL``) so the tenant context
    survives the ``commit()`` a mutation issues before its response resolvers
    read related rows. The scoped session is removed at the request boundary,
    and every entry point re-sets the context before its first query.
    """
    if not partition_key:
        raise ValueError("partition_key must be a non-empty string for RLS context.")

    session.execute(
        text("SET app.tenant_id = :tenant"),
        {"tenant": partition_key},
    )


def create_rls_policies(engine: Any) -> None:
    """Enable RLS and create tenant-isolation policies on all RFQ tables.


    Fast path (gateway-wedge fix 2026-10-20): tables that already have
    ``ENABLE`` + ``FORCE`` row level security and the
    ``tenant_isolation`` policy are skipped entirely, so the common
    per-request initialization takes no ``ACCESS EXCLUSIVE`` DDL locks.
    Previously every request ran 4 DDL statements per table; a single
    lingering read transaction (an uncommitted read-side SELECT
    anywhere) then blocked the next request's ALTERs and wedged the
    whole gateway dispatch pool while it held the queue.
    """
    from ..models.postgresql.base import prefixed_table

    with engine.connect() as conn:
        # Find (prefixed) table names where RLS is not yet fully applied.
        pending = [
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT t
                    FROM unnest(CAST(:names AS text[])) AS t
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_class c
                        WHERE c.relname = t
                          AND pg_table_is_visible(c.oid)
                          AND c.relrowsecurity
                          AND c.relforcerowsecurity
                          AND EXISTS (
                              SELECT 1
                              FROM pg_catalog.pg_policy pol
                              WHERE pol.polrelid = c.oid
                                AND pol.polname = 'tenant_isolation'
                          )
                    )
                    """
                ),
                {"names": [prefixed_table(t) for t in _RLS_TABLES]},
            ).fetchall()
        ]

        if not pending:
            logger.debug(
                "RLS policies verified for %d tables (fast path, no DDL).",
                len(_RLS_TABLES),
            )
            return
        for table_name in _RLS_TABLES:
            actual_name = prefixed_table(table_name)
            if actual_name not in pending:
                logger.debug(f"RLS already applied to {actual_name} (skip).")
                continue
            try:
                conn.execute(
                    text(f"ALTER TABLE {actual_name} ENABLE ROW LEVEL SECURITY")
                )
                conn.execute(
                    text(f"ALTER TABLE {actual_name} FORCE ROW LEVEL SECURITY")
                )
                conn.execute(
                    text(f"DROP POLICY IF EXISTS tenant_isolation ON {actual_name}")
                )
                conn.execute(
                    text(
                        f"CREATE POLICY tenant_isolation ON {actual_name} "
                        f"USING (partition_key = current_setting('app.tenant_id', true))"
                    )
                )
                logger.debug(f"RLS policy applied to {actual_name}")
            except Exception as exc:
                logger.warning(f"Failed to apply RLS to {actual_name}: {exc}")
        conn.commit()


__all__ = ["set_rls_context", "create_rls_policies", "_RLS_TABLES"]
