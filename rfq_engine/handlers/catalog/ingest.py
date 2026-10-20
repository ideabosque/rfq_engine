#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
RFQ → knowledge_engine ingestion bridge (NEW capability).

Pushes RFQ entities (item, provider_item, request, quote, bundle,
discount_prompt) and request files into the Banyanos ``knowledge_engine``
(KE) managed knowledge lifecycle through the public GraphQL API
(``createKnowledge`` / ``updateKnowledge`` / ``importKnowledge`` /
``importKnowledgeFromUrl``), invoked in-process via
``Invoker.invoke_funct_on_local`` under the ``knowledge_engine_graphql``
funct key.

Semantics (see docs/KGE_TO_KNOWLEDGE_ENGINE_MIGRATION_PLAN.md Phase 2):

- **Upsert by code** — ``code = {entity_type}-{uuid}`` is the stable KE
  identity; re-ingesting a changed entity updates the existing knowledge
  (optimistic-lock retry on version conflict), replaying an unchanged
  entity is a no-op.
- **Deterministic idempotency keys** — ``rfq:{partition_key}:{entity_type}:
  {uuid}:{updated_at/content hash}`` so retries deduplicate while changed
  entities produce fresh keys (KE idempotency window applies on top).
- **Markdown content projection** (decision D1) — KE's extraction and
  embedding pipeline is text-oriented.
- **Per-item in-band accounting** for batch ingestion (T2.5) and
  ``ItemCatalogRef`` auto-sync with ``node_id`` = KE knowledge id (T2.7).

Required settings (provisioned per tenant per Phase 0 T0.2):

- ``functs_on_local.knowledge_engine_graphql``
- ``knowledge_engine_ingest.domain_id`` — the provisioned KE domain
  (e.g. ``rfq-catalog``)
- ``knowledge_engine_ingest.type_ids.<entity_type>`` — provisioned KE
  knowledge type per RFQ entity type

Optional settings:

- ``knowledge_engine_ingest.namespace`` (default ``KE``) — ItemCatalogRef
  namespace for auto-synced refs
- ``knowledge_engine_ingest.sync_item_catalog_ref`` (default ``true``)
- ``knowledge_engine_ingest.max_concurrent_ingests`` (default ``10``)
- ``knowledge_engine_ingest.file_bucket`` — S3 bucket convention for
  generating presigned URLs when the caller does not supply one (D2)
"""
from __future__ import annotations

__author__ = "bibow"

import base64
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from graphene import ResolveInfo
from silvaengine_utility import Invoker

from ..config import Config
from ...models.repositories import get_repo
from .handler import (
    AccessDeniedError,
    CatalogHandlerError,
    ConfigurationError,
    NotFoundError,
    SystemError,
    SystemTimeoutError,
    _BIZ_ACCESS_CODES,
    _BIZ_CODE_RE,
    _BIZ_NOT_FOUND_CODES,
    _BIZ_TIMEOUT_CODES,
    _ke_context,
    _ke_setting,
)

# Statuses used for honest per-item accounting (T2.5).
STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_NOT_FOUND = "not_found"
STATUS_NOT_SUPPORTED = "not_supported"
STATUS_CONFIGURATION_ERROR = "configuration_error"
STATUS_ACCESS_DENIED = "access_denied"
STATUS_TIMEOUT = "system_timeout"
STATUS_ERROR = "error"

# Entity types supported by the bridge -> repository + lookup keys.
# ``parent`` marks lookup keys requiring a parent uuid (request for quote).
_ENTITY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "item": {
        "repo": "item",
        "uuid_key": "item_uuid",
        "keys": lambda uuid, parent: {"item_uuid": uuid},
        "label": lambda row: row.get("item_name"),
        "title": "Item",
    },
    "provider_item": {
        "repo": "provider_item",
        "uuid_key": "provider_item_uuid",
        "keys": lambda uuid, parent: {"provider_item_uuid": uuid},
        "label": lambda row: row.get("provider_item_external_id"),
        "title": "Provider Item",
    },
    "request": {
        "repo": "request",
        "uuid_key": "request_uuid",
        "keys": lambda uuid, parent: {"request_uuid": uuid},
        "label": lambda row: row.get("request_title"),
        "title": "Request",
    },
    "quote": {
        "repo": "quote",
        "uuid_key": "quote_uuid",
        "keys": lambda uuid, parent: {
            "quote_uuid": uuid,
            "request_uuid": parent,
        },
        "label": lambda row: f"Quote {row.get('quote_uuid')}",
        "title": "Quote",
    },
    "bundle": {
        "repo": "bundle",
        "uuid_key": "bundle_uuid",
        "keys": lambda uuid, parent: {"bundle_uuid": uuid},
        "label": lambda row: row.get("bundle_name"),
        "title": "Bundle",
    },
    "discount_prompt": {
        "repo": "discount_prompt",
        "uuid_key": "discount_prompt_uuid",
        "keys": lambda uuid, parent: {"discount_prompt_uuid": uuid},
        "label": lambda row: row.get("discount_prompt", "")[:80],
        "title": "Discount Prompt",
    },
}

# Ordered field projection for the markdown content (D1). ``None`` marks a
# section break: the preceding key renders as a prose block when present.
_PROJECTION_FIELDS: Dict[str, List[str]] = {
    "item": [
        "item_type",
        "item_name",
        "item_external_id",
        "pricing_mode",
        "uom",
        None,
        "item_description",
    ],
    "provider_item": [
        "provider_corp_external_id",
        "provider_item_external_id",
        "base_price_per_uom",
        "availability_mode",
        "item_uuid",
        None,
        "item_spec",
    ],
    "request": [
        "request_title",
        "email",
        "status",
        "expired_at",
        "bundle_uuid",
        None,
        "request_description",
        None,
        "billing_address",
        "shipping_address",
        "items",
        "notes",
    ],
    "quote": [
        "request_uuid",
        "provider_corp_external_id",
        "sales_rep_email",
        "status",
        "rounds",
        "shipping_method",
        "shipping_amount",
        "total_quote_amount",
        "total_quote_discount",
        "final_total_quote_amount",
        "currency",
        "display_currency",
        "fx_rate",
        None,
        "notes",
    ],
    "bundle": [
        "bundle_code",
        "bundle_name",
        "bundle_type",
        "status",
        None,
        "description",
        None,
        "extra",
    ],
    "discount_prompt": [
        "scope",
        "priority",
        "status",
        None,
        "discount_prompt",
        None,
        "conditions",
        "discount_rules",
        "tags",
    ],
}

_FIELD_LABELS = {
    "item_type": "Type",
    "item_name": "Name",
    "item_external_id": "External ID",
    "pricing_mode": "Pricing mode",
    "uom": "Unit of measure",
    "provider_corp_external_id": "Provider",
    "provider_item_external_id": "Provider item ID",
    "base_price_per_uom": "Base price per unit",
    "availability_mode": "Availability mode",
    "item_uuid": "Item UUID",
    "request_uuid": "Request UUID",
    "quote_uuid": "Quote UUID",
    "provider_item_uuid": "Provider item UUID",
    "bundle_uuid": "Bundle UUID",
    "discount_prompt_uuid": "Discount prompt UUID",
    "email": "Email",
    "status": "Status",
    "expired_at": "Expires at",
    "request_title": "Title",
    "sales_rep_email": "Sales rep",
    "rounds": "Rounds",
    "shipping_method": "Shipping method",
    "shipping_amount": "Shipping amount",
    "total_quote_amount": "Total quote amount",
    "total_quote_discount": "Total discount",
    "final_total_quote_amount": "Final total",
    "currency": "Currency",
    "display_currency": "Display currency",
    "fx_rate": "FX rate",
    "bundle_code": "Code",
    "bundle_name": "Name",
    "bundle_type": "Type",
    "scope": "Scope",
    "priority": "Priority",
}


# --------------------------------------------------------------------------- #
# KE GraphQL documents
# --------------------------------------------------------------------------- #

_KE_KNOWLEDGES_BY_CODE_QUERY = """
query KnowledgesByCode($filter: KnowledgeFilterInput, $first: Int) {
    knowledges(filter: $filter, first: $first) {
        edges { node { id code status content updatedAt } }
        totalCount
    }
}
"""

_KE_CREATE_KNOWLEDGE_MUTATION = """
mutation CreateKnowledge($input: KnowledgeCreateInput!, $idempotencyKey: ID!) {
    createKnowledge(input: $input, idempotencyKey: $idempotencyKey) {
        id
        code
        name
        typeId
        domainId
        status
        updatedAt
    }
}
"""

_KE_UPDATE_KNOWLEDGE_MUTATION = """
mutation UpdateKnowledge(
    $id: ID!,
    $input: KnowledgeUpdateInput!,
    $idempotencyKey: ID!
) {
    updateKnowledge(id: $id, input: $input, idempotencyKey: $idempotencyKey) {
        id
        code
        name
        typeId
        domainId
        status
        updatedAt
    }
}
"""

_KE_IMPORT_KNOWLEDGE_MUTATION = """
mutation ImportKnowledge($input: ImportKnowledgeInput!, $idempotencyKey: ID!) {
    importKnowledge(input: $input, idempotencyKey: $idempotencyKey) {
        sourceId
        filename
        size
        format
        status
        createdAt
    }
}
"""

_KE_IMPORT_URL_MUTATION = """
mutation ImportKnowledgeFromUrl($input: ImportUrlInput!, $idempotencyKey: ID!) {
    importKnowledgeFromUrl(input: $input, idempotencyKey: $idempotencyKey) {
        sourceId
        filename
        size
        format
        status
        createdAt
    }
}
"""

# Upsert retry budget: one retry covers the lost race / version conflict.
_UPSERT_ATTEMPTS = 2


# --------------------------------------------------------------------------- #
# Settings & helpers
# --------------------------------------------------------------------------- #


def _ingest_setting(setting: dict) -> dict:
    ingest_setting = setting.get("knowledge_engine_ingest")
    if not isinstance(ingest_setting, dict):
        return {}
    return ingest_setting


def _require_ingest_settings(setting: dict, entity_type: str) -> dict:
    """
    Fail fast when the tenant lacks provisioned KE domain/type ids (R2).

    RFQ never auto-creates KE domains or types at runtime.
    """
    ingest_setting = _ingest_setting(setting)
    domain_id = ingest_setting.get("domain_id")
    type_id = (ingest_setting.get("type_ids") or {}).get(entity_type)
    if not domain_id or not type_id:
        raise ConfigurationError(
            "knowledge_engine_ingest must be configured with domain_id and "
            f"type_ids.{entity_type} (provision the KE domain and types "
            "first; RFQ does not auto-create them)"
        )
    return {
        "domain_id": str(domain_id),
        "type_id": str(type_id),
        "namespace": str(ingest_setting.get("namespace", "KE")),
        "sync_item_catalog_ref": bool(
            ingest_setting.get("sync_item_catalog_ref", True)
        ),
        "max_concurrent_ingests": int(
            ingest_setting.get("max_concurrent_ingests", 10)
        ),
        "file_bucket": ingest_setting.get("file_bucket"),
    }


def _derive_idempotency_key(
    partition_key: str,
    entity_type: str,
    uuid: str,
    updated_at: Any,
    content: str,
) -> str:
    """
    Deterministic, replay-safe idempotency key (T2.4).

    Includes a hash of ``updated_at`` plus the projected content, so
    replaying an unchanged write deduplicates while a changed entity gets
    a fresh key (retries of stale writes are rejected by KE's idempotency
    window, not deduplicated — R5).
    """
    digest = hashlib.sha256(
        f"{updated_at}|{content}".encode("utf-8")
    ).hexdigest()[:16]
    return f"rfq:{partition_key}:{entity_type}:{uuid}:{digest}"


def _project_markdown(entity_type: str, row: dict) -> str:
    """Project a normalized entity row to markdown (decision D1)."""
    spec = _ENTITY_REGISTRY[entity_type]
    title = (spec["label"](row) or f"{spec['title']} {row.get(spec['uuid_key'])}").strip()
    lines: List[str] = [f"# {spec['title']}: {title}", ""]

    for field in _PROJECTION_FIELDS.get(entity_type, []):
        if field is None:
            continue
        value = row.get(field)
        if value is None or value == "" or value == []:
            continue
        label = _FIELD_LABELS.get(field, field.replace("_", " ").title())
        if field == "item_spec" and isinstance(value, dict):
            for key, spec_value in value.items():
                if spec_value in (None, ""):
                    continue
                lines.append(f"- **{key}**: {spec_value}")
        elif field.endswith("description") or field in (
            "discount_prompt",
            "notes",
        ):
            lines.append("")
            lines.append(str(value))
            lines.append("")
        elif isinstance(value, (dict, list)):
            lines.append(f"- **{label}**: {value}")
        else:
            lines.append(f"- **{label}**: {value}")

    # Prose section for description-like fields that render as blocks.
    lines.append("")
    lines.append(
        f"*Ingested from rfq_engine ({entity_type} "
        f"{row.get(spec['uuid_key'])}).*"
    )
    return "\n".join(lines)


def _tags_for(entity_type: str, row: dict) -> List[str]:
    tags = [entity_type, "rfq_engine"]
    if entity_type == "item" and row.get("item_type"):
        tags.append(str(row["item_type"]))
    if entity_type == "provider_item" and row.get("provider_corp_external_id"):
        tags.append(str(row["provider_corp_external_id"]))
    if entity_type == "bundle" and row.get("bundle_type"):
        tags.append(str(row["bundle_type"]))
    if entity_type == "discount_prompt" and row.get("scope"):
        tags.append(str(row["scope"]))
    return tags


def _fetch_entity(
    info: ResolveInfo,
    entity_type: str,
    uuid: str,
    parent_uuid: Optional[str],
) -> Optional[dict]:
    spec = _ENTITY_REGISTRY[entity_type]
    keys = spec["keys"](uuid, parent_uuid)
    keys.setdefault("partition_key", info.context.get("partition_key"))
    return get_repo(spec["repo"]).get(**keys)


def _map_ingest_error(
    exc: Exception, *, operation: str
) -> tuple[str, str]:
    """Map a KE invocation failure to (status, error_code) (T1.5/T2.2)."""
    message = str(exc)
    codes = set(_BIZ_CODE_RE.findall(message))
    if codes & _BIZ_TIMEOUT_CODES or "timeout" in message.lower() or (
        "timed out" in message.lower()
    ):
        return STATUS_TIMEOUT, SystemTimeoutError.code
    if codes & _BIZ_NOT_FOUND_CODES:
        return STATUS_NOT_FOUND, NotFoundError.code
    if codes & _BIZ_ACCESS_CODES:
        return STATUS_ACCESS_DENIED, AccessDeniedError.code
    return STATUS_ERROR, SystemError.code


def _invoke_knowledge_engine(
    info: ResolveInfo,
    setting: dict,
    query: str,
    variables: dict,
    *,
    operation: str,
) -> dict:
    """Invoke KE in-process (ingest path) and return the data payload."""
    if not (setting.get("functs_on_local") or {}).get("knowledge_engine_graphql"):
        raise ConfigurationError(
            "functs_on_local.knowledge_engine_graphql must be configured to "
            "route knowledge ingestion through Invoker.invoke_funct_on_local"
        )
    logger = info.context.get("logger") or logging.getLogger("catalog")
    try:
        data = Invoker.invoke_funct_on_local(
            logger,
            _ke_setting(setting),
            "knowledge_engine_graphql",
            query=query,
            variables=variables,
            endpoint_id=info.context.get("endpoint_id"),
            part_id=info.context.get("part_id"),
            context=_ke_context(info),
        )
    except CatalogHandlerError:
        raise
    except Exception as exc:
        status, error_code = _map_ingest_error(exc, operation=operation)
        message = f"Knowledge engine {operation} failed: {exc}"
        if error_code == SystemTimeoutError.code:
            raise SystemTimeoutError(message) from exc
        if error_code == NotFoundError.code:
            raise NotFoundError(message) from exc
        if error_code == AccessDeniedError.code:
            raise AccessDeniedError(message) from exc
        raise SystemError(message) from exc

    if not isinstance(data, dict):
        raise SystemError(f"Knowledge engine {operation} returned no data")
    return data


def _result(
    *,
    status: str,
    entity_type: Optional[str] = None,
    entity_uuid: Optional[str] = None,
    knowledge_id: Optional[str] = None,
    source_id: Optional[str] = None,
    domain_id: Optional[str] = None,
    type_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    """Normalized in-band result row (matches KnowledgeIngestResultType)."""
    return {
        "status": status,
        "entity_type": entity_type,
        "entity_uuid": entity_uuid,
        "knowledge_id": knowledge_id,
        "source_id": source_id,
        "domain_id": domain_id,
        "type_id": type_id,
        "idempotency_key": idempotency_key,
        "error_code": error_code,
        "error_message": error_message,
    }


# --------------------------------------------------------------------------- #
# Core upsert (T2.3/T2.4/T2.8)
# --------------------------------------------------------------------------- #


def _upsert_knowledge(
    info: ResolveInfo,
    setting: dict,
    *,
    entity_type: str,
    uuid: str,
    row: dict,
    provisioned: dict,
    idempotency_key: str,
) -> dict:
    """
    Create-or-update one KE knowledge entry keyed by ``code``.

    ``updateKnowledge`` enforces an ``expectedUpdatedAt`` optimistic lock;
    a version conflict (concurrent write) is retried once with a fresh
    lookup. A lost create race (``BIZ_KNOWLEDGE_ALREADY_EXISTS``) falls
    through to the update path.
    """
    spec = _ENTITY_REGISTRY[entity_type]
    code = f"{entity_type}-{uuid}"
    name = (spec["label"](row) or code).strip()
    content = _project_markdown(entity_type, row)
    updated_at = row.get("updated_at") or row.get("created_at")
    metadata = {
        "source": "rfq_engine",
        "entity_type": entity_type,
        "uuid": uuid,
        "endpoint_id": info.context.get("endpoint_id"),
        "updated_at": str(updated_at) if updated_at else None,
    }
    tags = _tags_for(entity_type, row)

    for attempt in range(_UPSERT_ATTEMPTS):
        lookup = _invoke_knowledge_engine(
            info,
            setting,
            _KE_KNOWLEDGES_BY_CODE_QUERY,
            {"filter": {"code": code}, "first": 1},
            operation="knowledges_by_code",
        ).get("knowledges")
        edges = ((lookup or {}).get("edges")) or []
        existing = edges[0].get("node") if edges else None

        if not existing:
            create_input = {
                "code": code,
                "name": name,
                "typeId": provisioned["type_id"],
                "domainId": provisioned["domain_id"],
                "content": content,
                "metadata": metadata,
                "tags": tags,
                "automaticVectorization": True,
            }
            try:
                created = _invoke_knowledge_engine(
                    info,
                    setting,
                    _KE_CREATE_KNOWLEDGE_MUTATION,
                    {"input": create_input, "idempotencyKey": idempotency_key},
                    operation="createKnowledge",
                ).get("createKnowledge")
                if not isinstance(created, dict):
                    raise SystemError("createKnowledge returned no payload")
                return _result(
                    status=STATUS_OK,
                    entity_type=entity_type,
                    entity_uuid=uuid,
                    knowledge_id=str(created.get("id")),
                    domain_id=str(created.get("domainId") or provisioned["domain_id"]),
                    type_id=str(created.get("typeId") or provisioned["type_id"]),
                    idempotency_key=idempotency_key,
                )
            except SystemError as exc:
                # Lost create race -> fall through to the update path below.
                if "BIZ_KNOWLEDGE_ALREADY_EXISTS" not in str(exc):
                    raise
                continue

        # Existing entry: replay of unchanged content is a no-op (T2.4).
        if existing.get("content") == content:
            return _result(
                status=STATUS_OK,
                entity_type=entity_type,
                entity_uuid=uuid,
                knowledge_id=str(existing.get("id")),
                domain_id=provisioned["domain_id"],
                type_id=provisioned["type_id"],
                idempotency_key=idempotency_key,
            )

        update_input = {
            "name": name,
            "content": content,
            "metadata": metadata,
            "tags": tags,
            "expectedUpdatedAt": existing.get("updatedAt"),
        }
        try:
            updated = _invoke_knowledge_engine(
                info,
                setting,
                _KE_UPDATE_KNOWLEDGE_MUTATION,
                {
                    "id": str(existing.get("id")),
                    "input": update_input,
                    "idempotencyKey": idempotency_key,
                },
                operation="updateKnowledge",
            ).get("updateKnowledge")
            if not isinstance(updated, dict):
                raise SystemError("updateKnowledge returned no payload")
            return _result(
                status=STATUS_OK,
                entity_type=entity_type,
                entity_uuid=uuid,
                knowledge_id=str(updated.get("id")),
                domain_id=str(updated.get("domainId") or provisioned["domain_id"]),
                type_id=str(updated.get("typeId") or provisioned["type_id"]),
                idempotency_key=idempotency_key,
            )
        except SystemError as exc:
            # Version conflict -> retry once with a fresh expectedUpdatedAt.
            if "BIZ_KNOWLEDGE_VERSION_CONFLICT" not in str(exc):
                raise
            if attempt == _UPSERT_ATTEMPTS - 1:
                raise

    raise SystemError(f"Knowledge upsert for {code} exhausted retries")


def _sync_catalog_ref(
    info: ResolveInfo,
    *,
    entity_type: str,
    uuid: str,
    provider_item_uuid: Optional[str],
    knowledge_id: str,
    namespace: str,
) -> None:
    """
    Auto-create/update the ``ItemCatalogRef`` bridge row with
    ``node_id`` = KE knowledge id (T2.7). Best-effort: a sync failure is
    logged, never fatal to the ingestion result.
    """
    if not (entity_type in ("item", "provider_item") and uuid):
        return
    try:
        get_repo("item_catalog_ref").insert_update(
            info,
            namespace=namespace,
            node_id=str(knowledge_id),
            item_uuid=uuid if entity_type == "item" else None,
            provider_item_uuid=provider_item_uuid
            or (uuid if entity_type == "provider_item" else None),
            status="active",
            updated_by="rfq_knowledge_ingest",
        )
    except Exception as exc:  # noqa: BLE001
        logger = info.context.get("logger")
        if logger:
            logger.warning(
                "catalog ref sync failed for %s %s (node_id=%s): %s",
                entity_type,
                uuid,
                knowledge_id,
                exc,
            )


def _maybe_sync_catalog_ref(
    info: ResolveInfo,
    entity_type: str,
    uuid: str,
    result: dict,
    provisioned: dict,
    provider_item_uuid: Optional[str] = None,
) -> dict:
    if (
        result.get("status") == STATUS_OK
        and result.get("knowledge_id")
        and provisioned["sync_item_catalog_ref"]
    ):
        _sync_catalog_ref(
            info,
            entity_type=entity_type,
            uuid=uuid,
            provider_item_uuid=provider_item_uuid,
            knowledge_id=str(result["knowledge_id"]),
            namespace=provisioned["namespace"],
        )
    return result


def _error_result(
    exc: Exception,
    *,
    entity_type: Optional[str],
    uuid: Optional[str],
    idempotency_key: Optional[str] = None,
    provisioned: Optional[dict] = None,
) -> dict:
    status = STATUS_ERROR
    error_code = SystemError.code
    if isinstance(exc, CatalogHandlerError):
        error_code = exc.code
        status = {
            ConfigurationError.code: STATUS_CONFIGURATION_ERROR,
            AccessDeniedError.code: STATUS_ACCESS_DENIED,
            SystemTimeoutError.code: STATUS_TIMEOUT,
            NotFoundError.code: STATUS_NOT_FOUND,
        }.get(exc.code, STATUS_ERROR)
    return _result(
        status=status,
        entity_type=entity_type,
        entity_uuid=uuid,
        domain_id=(provisioned or {}).get("domain_id"),
        type_id=(provisioned or {}).get("type_id"),
        idempotency_key=idempotency_key,
        error_code=error_code,
        error_message=str(exc),
    )


# --------------------------------------------------------------------------- #
# Public dispatch boundaries (T2.1)
# --------------------------------------------------------------------------- #


def dispatch_ingest_knowledge(
    info: ResolveInfo,
    *,
    entity_type: str,
    uuid: str,
    parent_uuid: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Ingest one RFQ entity into the knowledge engine.

    Returns an in-band result dict (``KnowledgeIngestResultType`` shape);
    failures are reported through ``status``/``error_code``/
    ``error_message`` rather than raised.
    """
    from ..telemetry import measure_handler_duration

    with measure_handler_duration(
        info, operation="ingest", handler="catalog", namespace=entity_type
    ):
        entity_type = str(entity_type or "").strip().lower()
        uuid = str(uuid or "").strip()
        partition_key = info.context.get("partition_key")
        if not partition_key:
            raise SystemError("partition_key is required for knowledge ingestion")

        spec = _ENTITY_REGISTRY.get(entity_type)
        if spec is None or not uuid:
            return _result(
                status=STATUS_NOT_SUPPORTED,
                entity_type=entity_type,
                entity_uuid=uuid or None,
                error_code="operation_unsupported",
                error_message=(
                    f"Unsupported entity type {entity_type!r}; supported: "
                    + ", ".join(sorted(_ENTITY_REGISTRY))
                ),
            )

        setting = Config.get_setting()
        try:
            provisioned = _require_ingest_settings(setting, entity_type)
        except ConfigurationError as exc:
            return _error_result(
                exc, entity_type=entity_type, uuid=uuid
            )

        try:
            row = _fetch_entity(info, entity_type, uuid, parent_uuid)
        except Exception as exc:  # noqa: BLE001
            return _error_result(exc, entity_type=entity_type, uuid=uuid)

        if not row:
            return _result(
                status=STATUS_NOT_FOUND,
                entity_type=entity_type,
                entity_uuid=uuid,
                domain_id=provisioned["domain_id"],
                type_id=provisioned["type_id"],
                error_code=NotFoundError.code,
                error_message=f"{entity_type} {uuid} not found",
            )

        content = _project_markdown(entity_type, row)
        derived = _derive_idempotency_key(
            partition_key,
            entity_type,
            uuid,
            row.get("updated_at") or row.get("created_at"),
            content,
        )
        key = f"{idempotency_key}:{derived}" if idempotency_key else derived

        try:
            result = _upsert_knowledge(
                info,
                setting,
                entity_type=entity_type,
                uuid=uuid,
                row=row,
                provisioned=provisioned,
                idempotency_key=key,
            )
        except CatalogHandlerError as exc:
            return _error_result(
                exc,
                entity_type=entity_type,
                uuid=uuid,
                idempotency_key=key,
                provisioned=provisioned,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_result(
                exc,
                entity_type=entity_type,
                uuid=uuid,
                idempotency_key=key,
                provisioned=provisioned,
            )

        return _maybe_sync_catalog_ref(
            info, entity_type, uuid, result, provisioned
        )


def dispatch_ingest_catalog(
    info: ResolveInfo,
    *,
    item_uuids: List[str],
    include_provider_items: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Batch-ingest catalog items (plus their provider items) into the
    knowledge engine (T2.5).

    Iterates with bounded concurrency (``max_concurrent_ingests``) and
    returns per-item in-band result rows (``ok`` / ``not_found`` /
    ``configuration_error`` / ``access_denied`` / ``system_timeout`` /
    ``error``) plus requested/ingested/failed counters — honest partial-
    failure attribution like KE's own batch operations.
    """
    from ..telemetry import measure_handler_duration

    with measure_handler_duration(
        info, operation="ingest_catalog", handler="catalog", namespace="batch"
    ):
        if not isinstance(item_uuids, list) or not item_uuids:
            raise SystemError("item_uuids must be a non-empty list")

        partition_key = info.context.get("partition_key")
        if not partition_key:
            raise SystemError("partition_key is required for knowledge ingestion")

        setting = Config.get_setting()
        try:
            item_provisioned = _require_ingest_settings(setting, "item")
            max_workers = item_provisioned["max_concurrent_ingests"]
        except ConfigurationError as exc:
            # Configuration failure fails the whole batch in-band.
            return {
                "requested": len(item_uuids),
                "ingested": 0,
                "failed": len(item_uuids),
                "results": [
                    _error_result(
                        exc, entity_type="item", uuid=str(u)
                    )
                    for u in item_uuids
                ],
            }

        # Expand the requested items into work units:
        # (entity_type, uuid, parent_or_provider_uuid).
        work: List[tuple] = []
        for item_uuid in item_uuids:
            work.append(("item", str(item_uuid), None))
        if include_provider_items:
            for item_uuid in item_uuids:
                try:
                    provider_items = get_repo("provider_item").list(
                        info, item_uuid=str(item_uuid), limit=100
                    )
                    provider_list = (
                        getattr(provider_items, "provider_item_list", None) or []
                    )
                except Exception:  # noqa: BLE001
                    provider_list = []
                for provider_item in provider_list:
                    provider_uuid = getattr(
                        provider_item, "provider_item_uuid", None
                    ) or (
                        provider_item.get("provider_item_uuid")
                        if isinstance(provider_item, dict)
                        else None
                    )
                    if provider_uuid:
                        work.append(("provider_item", str(provider_uuid), str(item_uuid)))

        def _ingest_one(unit: tuple) -> dict:
            entity_type, uuid, parent_uuid = unit
            return dispatch_ingest_knowledge(
                info,
                entity_type=entity_type,
                uuid=uuid,
                parent_uuid=parent_uuid,
                idempotency_key=idempotency_key,
            )

        results: List[dict] = []
        workers = max(1, min(int(max_workers), 10))
        if len(work) == 1:
            results = [_ingest_one(work[0])]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_ingest_one, unit) for unit in work}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as exc:  # noqa: BLE001
                        results.append(
                            _error_result(exc, entity_type=None, uuid=None)
                        )

        ingested = sum(1 for r in results if r.get("status") == STATUS_OK)
        failed = sum(
            1
            for r in results
            if r.get("status")
            not in (STATUS_OK, STATUS_SKIPPED)
        )
        return {
            "requested": len(work),
            "ingested": ingested,
            "failed": failed,
            "results": results,
        }


def dispatch_ingest_file(
    info: ResolveInfo,
    *,
    request_uuid: str,
    file_name: str,
    file_url: Optional[str] = None,
    file_content: Optional[str] = None,
    file_format: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Push one RFQ request file into the knowledge engine (T2.6).

    Transport (decision D2): a caller-supplied or S3-generated presigned
    URL via ``importKnowledgeFromUrl`` (size-safe), or inline base64 via
    ``importKnowledge`` for small files. The KE pipeline handles parse /
    chunk / PII masking.
    """
    from ..telemetry import measure_handler_duration

    with measure_handler_duration(
        info, operation="ingest_file", handler="catalog", namespace="file"
    ):
        partition_key = info.context.get("partition_key")
        if not partition_key:
            raise SystemError("partition_key is required for knowledge ingestion")

        request_uuid = str(request_uuid or "").strip()
        file_name = str(file_name or "").strip()
        if not request_uuid or not file_name:
            raise SystemError("request_uuid and file_name are required")

        setting = Config.get_setting()
        try:
            provisioned = _require_ingest_settings(setting, "item")
        except ConfigurationError as exc:
            return _error_result(
                exc, entity_type="file", uuid=file_name
            )

        try:
            file_row = get_repo("file").get(
                request_uuid=request_uuid, file_name=file_name
            )
        except Exception as exc:  # noqa: BLE001
            return _error_result(exc, entity_type="file", uuid=file_name)
        if not file_row:
            return _result(
                status=STATUS_NOT_FOUND,
                entity_type="file",
                entity_uuid=file_name,
                domain_id=provisioned["domain_id"],
                error_code=NotFoundError.code,
                error_message=f"File {file_name} not found on request {request_uuid}",
            )

        url = file_url
        if not url and file_content is None:
            url = _presigned_file_url(setting, request_uuid, file_name)
            if not url:
                return _result(
                    status=STATUS_CONFIGURATION_ERROR,
                    entity_type="file",
                    entity_uuid=file_name,
                    domain_id=provisioned["domain_id"],
                    error_code=ConfigurationError.code,
                    error_message=(
                        "No transport for file ingestion: provide file_url "
                        "or file_content, or configure "
                        "knowledge_engine_ingest.file_bucket (presigned URL "
                        "fallback)"
                    ),
                )

        derived = _derive_idempotency_key(
            partition_key,
            "file",
            f"{request_uuid}-{file_name}",
            file_row.get("updated_at") or file_row.get("created_at"),
            url or hashlib.sha256(str(file_content).encode()).hexdigest(),
        )
        key = f"{idempotency_key}:{derived}" if idempotency_key else derived

        try:
            if url:
                data = _invoke_knowledge_engine(
                    info,
                    setting,
                    _KE_IMPORT_URL_MUTATION,
                    {
                        "input": {
                            "url": url,
                            "knowledgeTypeId": provisioned["type_id"],
                            "domainId": provisioned["domain_id"],
                        },
                        "idempotencyKey": key,
                    },
                    operation="importKnowledgeFromUrl",
                ).get("importKnowledgeFromUrl")
            else:
                # Validate base64 eagerly so transport errors are ours.
                try:
                    base64.b64decode(str(file_content), validate=True)
                except Exception as exc:  # noqa: BLE001
                    raise SystemError(
                        f"file_content is not valid base64: {exc}"
                    ) from exc
                data = _invoke_knowledge_engine(
                    info,
                    setting,
                    _KE_IMPORT_KNOWLEDGE_MUTATION,
                    {
                        "input": {
                            "fileName": file_name,
                            "fileContent": str(file_content),
                            "fileFormat": file_format,
                            "knowledgeTypeId": provisioned["type_id"],
                            "domainId": provisioned["domain_id"],
                        },
                        "idempotencyKey": key,
                    },
                    operation="importKnowledge",
                ).get("importKnowledge")
        except CatalogHandlerError as exc:
            return _error_result(
                exc,
                entity_type="file",
                uuid=file_name,
                idempotency_key=key,
                provisioned=provisioned,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_result(
                exc,
                entity_type="file",
                uuid=file_name,
                idempotency_key=key,
                provisioned=provisioned,
            )

        if not isinstance(data, dict):
            return _result(
                status=STATUS_ERROR,
                entity_type="file",
                entity_uuid=file_name,
                domain_id=provisioned["domain_id"],
                idempotency_key=key,
                error_code=SystemError.code,
                error_message="Knowledge engine returned no import payload",
            )

        return _result(
            status=STATUS_OK,
            entity_type="file",
            entity_uuid=file_name,
            source_id=str(data.get("sourceId")),
            domain_id=provisioned["domain_id"],
            type_id=provisioned["type_id"],
            idempotency_key=key,
        )


def _presigned_file_url(
    setting: dict, request_uuid: str, file_name: str
) -> Optional[str]:
    """Generate a presigned S3 URL for the conventional file location (D2)."""
    bucket = _ingest_setting(setting).get("file_bucket")
    s3 = Config.aws_s3
    if not bucket or s3 is None:
        return None
    key = f"{request_uuid}/{file_name}"
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": str(bucket), "Key": key},
            ExpiresIn=3600,
        )
    except Exception:  # noqa: BLE001
        return None