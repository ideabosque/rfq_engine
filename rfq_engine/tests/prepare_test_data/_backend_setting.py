# -*- coding: utf-8 -*-
"""Shared setting builder for dual-backend seed scripts.

All ``prepare_test_data/*.py`` scripts import :func:`build_setting` instead
of inlining the ``SETTING`` dict. The active backend is selected by the
``DB_BACKEND`` env var (``dynamodb`` default, ``postgresql`` for the local
PostgreSQL seed path). PostgreSQL connection values come from
``DATABASE_URL`` or the ``PG_*`` env vars; DynamoDB values come from the
existing ``region_name`` / ``aws_access_key_id`` / ``aws_secret_access_key``
keys in ``tests/.env``.

The helper keeps every seed script backend-agnostic: the repository
dispatch boundary in ``rfq_engine.models.repositories`` routes GraphQL
persistence to the active backend, so the scripts do not need any
backend-specific mutation logic.
"""
from __future__ import annotations

__author__ = "bibow"

import os
import sys
from typing import Any, Dict


def _ensure_sibling_paths() -> None:
    """Add silvaengine sibling repos to ``sys.path`` if not already present.

    Mirrors the path setup in ``tests/conftest.py`` so the seed scripts can
    import ``rfq_engine``, ``silvaengine_utility``, and
    ``silvaengine_constants`` without relying on the conftest fixture.

    ``base_dir`` is read from the env var (populated by the script's own
    ``load_dotenv`` call before this helper is imported) and points at the
    silvaengine source root that *contains* ``rfq_engine`` as a sibling.
    """
    base_dir = os.getenv("base_dir") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    for sibling in ("silvaengine_utility", "silvaengine_dynamodb_base",
                    "silvaengine_constants", "rfq_engine"):
        path = os.path.join(base_dir, sibling)
        if path and path not in sys.path:
            sys.path.insert(0, path)


_ensure_sibling_paths()


def build_setting() -> Dict[str, Any]:
    """Build the ``SETTING`` dict for ``RFQEngine`` based on ``DB_BACKEND``.

    Reads ``DB_BACKEND`` (default ``"dynamodb"``). When ``postgresql``:

    * ``db_backend`` is included so ``Config.initialize`` selects the PG path.
    * ``db_host`` / ``db_port`` / ``db_user`` / ``db_password`` / ``db_schema``
      are populated from ``PG_HOST`` / ``PG_PORT`` / ``PG_USER`` /
      ``PG_PASSWORD`` / ``PG_DB`` (or parsed out of ``DATABASE_URL`` when set).
    * AWS credential keys are still passed through so optional AWS services
      (S3 for File) can initialize when all three credential fields are
      present; they are omitted otherwise.

    When ``dynamodb`` the dict is the legacy shape used by every existing
    seed script, unchanged.
    """
    backend = (os.getenv("DB_BACKEND") or "dynamodb").lower()

    setting: Dict[str, Any] = {
        "functs_on_local": {
            "ai_rfq_graphql": {
                "module_name": "rfq_engine",
                "class_name": "RFQEngine",
            },
        },
        "endpoint_id": os.getenv("endpoint_id"),
        "part_id": os.getenv("part_id"),
        "execute_mode": os.getenv("execute_mode", "local"),
        "initialize_tables": os.getenv("initialize_tables", "0") == "1",
        "cache_enabled": os.getenv("cache_enabled", "0") == "1",
    }

    aws_key = os.getenv("aws_access_key_id")
    aws_secret = os.getenv("aws_secret_access_key")
    aws_region = os.getenv("region_name")
    if aws_key and aws_secret and aws_region:
        setting["region_name"] = aws_region
        setting["aws_access_key_id"] = aws_key
        setting["aws_secret_access_key"] = aws_secret

    if backend == "postgresql":
        setting["db_backend"] = "postgresql"
        pg = _resolve_pg_connection()
        setting.update(pg)
    else:
        setting["db_backend"] = "dynamodb"

    return setting


def _resolve_pg_connection() -> Dict[str, Any]:
    """Return ``db_host`` / ``db_port`` / ... from env vars or ``DATABASE_URL``."""
    url = os.getenv("DATABASE_URL")
    if url:
        # Parse ``postgresql+psycopg2://user:pass@host:port/db``
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return {
            "db_host": parsed.hostname or "localhost",
            "db_port": int(parsed.port or 5432),
            "db_user": parsed.username or "silvaengine",
            "db_password": parsed.password or "silvaengine",
            "db_schema": (parsed.path or "/silvaengine").lstrip("/"),
        }

    return {
        "db_host": os.getenv("PG_HOST", "localhost"),
        "db_port": int(os.getenv("PG_PORT", "5432")),
        "db_user": os.getenv("PG_USER", "silvaengine"),
        "db_password": os.getenv("PG_PASSWORD", "silvaengine"),
        "db_schema": os.getenv("PG_DB", "silvaengine"),
    }


__all__ = ["build_setting"]