#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Knowledge-engine backed catalog inquiry boundary.

Routes ``inquire_catalog`` to the Banyanos ``knowledge_engine`` (KE) public
GraphQL API (funct ``knowledge_engine_graphql``) in-process via
``Invoker.invoke_funct_on_local``. Supports four inquiry modes behind the
existing ``query.search_mode`` argument (``semantic`` default, ``ask``,
``graph``, ``cypher``) plus node-by-id lookup via ``node_id`` (KE
``knowledge(id)``).

The legacy ``knowledge_graph_engine`` (KGE) path is retained behind the
transitional ``catalog_knowledge_backend: "kge"`` setting for dual-run and
rollback during the migration (see
``docs/KGE_TO_KNOWLEDGE_ENGINE_MIGRATION_PLAN.md`` T4.1/T4.4); it is removed
at Phase 4 hard cutover (T4.3).
"""
from __future__ import annotations

__author__ = "bibow"

import logging
import re
from typing import Any, Optional, TypedDict

import pendulum
from graphene import ResolveInfo
from silvaengine_utility import Invoker

from ..config import Config


class CatalogReference(TypedDict):
    namespace: str
    node_id: Optional[str]


class CatalogResponse(TypedDict, total=False):
    ref: CatalogReference
    payload: Any
    fetched_at: str
    ttl_seconds: Optional[int]


class CatalogHandlerError(Exception):
    code = "system_error"

    def __init__(self, message: str = "", *, details: Optional[dict] = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.details = details or {}


class SystemTimeoutError(CatalogHandlerError):
    code = "system_timeout"


class SystemError(CatalogHandlerError):
    code = "system_error"


class OperationUnsupportedError(CatalogHandlerError):
    code = "operation_unsupported"


class NotFoundError(CatalogHandlerError):
    """Requested node/knowledge does not exist in the knowledge engine."""

    code = "not_found"


class AccessDeniedError(CatalogHandlerError):
    """Knowledge engine rejected the caller's identity/permissions."""

    code = "access_denied"


class ConfigurationError(CatalogHandlerError):
    """The knowledge-engine integration is not configured for this tenant."""

    code = "configuration_error"


# --------------------------------------------------------------------------- #
# Knowledge engine (KE) query documents
# --------------------------------------------------------------------------- #

_KE_SEARCH_QUERY = """
query SearchKnowledges($query: String!, $limit: Int, $domainIds: [ID]) {
    searchKnowledges(query: $query, limit: $limit, domainIds: $domainIds) {
        id
        code
        name
        typeId
        domainId
        status
        tags
        updatedAt
    }
}
"""

_KE_KNOWLEDGE_QUERY = """
query Knowledge($id: ID!) {
    knowledge(id: $id) {
        id
        code
        name
        typeId
        domainId
        status
        content
        metadata
        tags
        createdAt
        updatedAt
        createdBy
        isDeleted
    }
}
"""

_KE_ASK_QUERY = """
query AskKnowledgeBase(
    $question: String!,
    $domainIds: [ID],
    $maxHops: Int,
    $topK: Int,
    $rerankTopK: Int,
    $sourceLevels: [String]
) {
    askKnowledgeBase(
        question: $question,
        domainIds: $domainIds,
        maxHops: $maxHops,
        topK: $topK,
        rerankTopK: $rerankTopK,
        sourceLevels: $sourceLevels
    ) {
        answer
        confidence
        sources
        graphPaths
        retrievedChunks
        usage
    }
}
"""

_KE_GRAPH_QUERY = """
query KnowledgeGraph($domainIds: [ID], $depth: Int, $limit: Int) {
    knowledgeGraph(domainIds: $domainIds, depth: $depth, limit: $limit) {
        nodes { id name label type properties degree }
        edges { id source target type label properties weight }
        totalNodes
        totalEdges
    }
}
"""

_KE_CYPHER_QUERY = """
query KnowledgeGraphByCypher($cypher: String!, $limit: Int) {
    knowledgeGraphByCypher(cypher: $cypher, limit: $limit) {
        nodes { id name label type properties degree }
        edges { id source target type label properties weight }
        totalNodes
        totalEdges
    }
}
"""


# --------------------------------------------------------------------------- #
# Legacy KGE query document (dual-run/rollback path — removed at T4.3)
# --------------------------------------------------------------------------- #

_KGE_SEARCH_QUERY = """
query Search(
    $queryText: String!,
    $searchMode: String,
    $indexName: String,
    $retrievalQuery: String,
    $filters: JSONCamelCase,
    $topK: Int,
    $page: Int,
    $limit: Int
) {
    search(
        queryText: $queryText,
        searchMode: $searchMode,
        indexName: $indexName,
        retrievalQuery: $retrievalQuery,
        filters: $filters,
        topK: $topK,
        page: $page,
        limit: $limit
    ) {
        results
        query
        total
        page
        limit
    }
}
"""


# --------------------------------------------------------------------------- #
# Mode mapping (RFQ inquiry mode -> KE operation)
# --------------------------------------------------------------------------- #

# Canonical RFQ modes.
_MODE_SEARCH = "search"
_MODE_ASK = "ask"
_MODE_GRAPH = "graph"
_MODE_CYPHER = "cypher"

# RFQ mode -> KE operation, including legacy KGE mode names mapped to their
# nearest KE equivalent (logged at dispatch time; see T1.4).
_MODE_MAP = {
    "semantic": _MODE_SEARCH,
    "ask": _MODE_ASK,
    "graph": _MODE_GRAPH,
    "cypher": _MODE_CYPHER,
    # Legacy KGE modes (documented in the migration plan §3.2):
    "text2cypher": _MODE_CYPHER,
    "vector": _MODE_SEARCH,
    "hybrid": _MODE_SEARCH,
}

# KE clamps search limits to 100 (searchKnowledges docstring).
_KE_SEARCH_LIMIT_MAX = 100
_KE_SEARCH_LIMIT_DEFAULT = 10

# BIZ_KNOWLEDGE_* error-code fragments -> CatalogHandlerError subclass.
_BIZ_TIMEOUT_CODES = {"BIZ_KNOWLEDGE_TIMEOUT", "BIZ_KNOWLEDGE_LLM_TIMEOUT"}
_BIZ_NOT_FOUND_CODES = {
    "BIZ_KNOWLEDGE_NOT_FOUND",
    "BIZ_KNOWLEDGE_TYPE_NOT_FOUND",
    "BIZ_KNOWLEDGE_DOMAIN_NOT_FOUND",
    "BIZ_KNOWLEDGE_SOURCE_NOT_FOUND",
}
_BIZ_ACCESS_CODES = {
    "BIZ_KNOWLEDGE_ACCESS_DENIED",
    "BIZ_KNOWLEDGE_PERMISSION",
    "BIZ_KNOWLEDGE_ADMIN_REQUIRED",
}

_BIZ_CODE_RE = re.compile(r"BIZ_KNOWLEDGE_[A-Z0-9_]+")


def _partition_key(info: ResolveInfo) -> str:
    partition_key = info.context.get("partition_key")
    if not partition_key:
        raise SystemError("partition_key is required for knowledge catalog inquiry")
    return partition_key


def _backend(setting: dict) -> str:
    """Transitional backend selection (T4.1). Default: knowledge_engine."""
    backend = str(setting.get("catalog_knowledge_backend", "knowledge_engine"))
    backend = backend.strip().lower()
    if backend in ("ke", "knowledge-engine"):
        backend = "knowledge_engine"
    return backend


def _ke_setting(setting: dict) -> dict:
    """
    Build the setting dict handed to the KE engine instance.

    The Invoker constructs a fresh ``KnowledgeEngine(logger, **setting)``
    per call; KE's ``Config.initialize`` is idempotent-guarded, so in
    gateway deployments (KE route-mounted and initialized at startup) this
    dict is inert. To keep a first-call initialization from inheriting
    RFQ-specific values that would misconfigure KE (risk R4), the RFQ
    backend-selection keys are stripped and any ``knowledge_engine_setting``
    overrides (KE config groups: llm, neo4j, minio, ...) are merged on top.
    """
    ke_setting = {
        key: value
        for key, value in setting.items()
        if key not in ("db_backend", "initialize_tables", "pg_table_prefix")
    }
    overrides = setting.get("knowledge_engine_setting")
    if isinstance(overrides, dict):
        ke_setting.update(overrides)
    return ke_setting


def _ke_context(info: ResolveInfo) -> dict:
    """
    Forward caller identity claims to the KE GraphQL context.

    KE isolates rows by the ``tenant_id`` claim and enforces
    ``knowledge:read``/``knowledge:write`` permissions from
    ``roles``/``permissions`` claims; without them mutations and
    per-resource access checks fail closed. The gateway injects these
    claims into RFQ's own context, so they are passed through 1:1.
    """
    context: dict[str, Any] = {
        "partition_key": info.context.get("partition_key"),
    }
    for key in (
        "user",
        "tenant_id",
        "user_id",
        "operator_id",
        "roles",
        "permissions",
        "is_admin",
    ):
        value = info.context.get(key)
        if value is not None:
            context[key] = value
    return context


def _map_engine_error(exc: Exception, *, operation: str) -> None:
    """
    Translate a knowledge-engine invocation failure into an in-band
    ``CatalogHandlerError`` (T1.5) and raise it.

    Prefers structured ``BIZ_KNOWLEDGE_*`` codes embedded in the GraphQL
    error payload; falls back to the legacy timeout string sniff as
    belt-and-braces.
    """
    message = str(exc)
    codes = set(_BIZ_CODE_RE.findall(message))

    if codes & _BIZ_TIMEOUT_CODES:
        raise SystemTimeoutError(
            "Knowledge engine catalog inquiry timed out"
        ) from exc
    if codes & _BIZ_NOT_FOUND_CODES:
        raise NotFoundError(
            f"Knowledge engine resource not found: {message}"
        ) from exc
    if codes & _BIZ_ACCESS_CODES:
        raise AccessDeniedError(
            "Knowledge engine rejected the inquiry access"
        ) from exc

    lowered = message.lower()
    if "timeout" in lowered or "timed out" in lowered:
        raise SystemTimeoutError(
            "Knowledge engine catalog inquiry timed out"
        ) from exc
    raise SystemError(
        f"Knowledge engine catalog inquiry failed: {exc}"
    ) from exc


def _invoke_knowledge_engine(
    info: ResolveInfo,
    setting: dict,
    query: str,
    variables: dict[str, Any],
    *,
    operation: str,
) -> dict:
    """Invoke KE in-process and return the GraphQL ``data`` payload."""
    if not (setting.get("functs_on_local") or {}).get("knowledge_engine_graphql"):
        raise ConfigurationError(
            "functs_on_local.knowledge_engine_graphql must be configured to "
            "route catalog inquiries through Invoker.invoke_funct_on_local"
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
        _map_engine_error(exc, operation=operation)

    if not isinstance(data, dict):
        raise SystemError("Knowledge engine invocation returned no data")
    return data


def _response(
    reference: CatalogReference, payload: Any
) -> CatalogResponse:
    return {
        "ref": reference,
        "payload": payload,
        "fetched_at": pendulum.now("UTC").to_iso8601_string(),
        "ttl_seconds": None,
    }


def _domain_ids(query: dict[str, Any]) -> Optional[list]:
    """Map the legacy KGE ``filters.domain_ids`` argument to ``domainIds``."""
    filters = query.get("filters")
    if isinstance(filters, dict):
        domain_ids = filters.get("domain_ids")
        if isinstance(domain_ids, list) and domain_ids:
            return [str(d) for d in domain_ids]
    return None


# --------------------------------------------------------------------------- #
# KE inquiry implementations (one per mode)
# --------------------------------------------------------------------------- #


def _search_inquiry(
    info: ResolveInfo,
    reference: CatalogReference,
    setting: dict,
    query: dict[str, Any],
) -> CatalogResponse:
    """``semantic`` mode — KE ``searchKnowledges`` (replaces KGE ``search``)."""
    query_text = query.get("query_text")
    if not query_text:
        raise SystemError("Catalog inquiry requires query.query_text")

    limit = query.get("limit") or query.get("top_k") or _KE_SEARCH_LIMIT_DEFAULT
    try:
        limit = max(1, min(int(limit), _KE_SEARCH_LIMIT_MAX))
    except (TypeError, ValueError):
        limit = _KE_SEARCH_LIMIT_DEFAULT

    data = _invoke_knowledge_engine(
        info,
        setting,
        _KE_SEARCH_QUERY,
        {
            "query": query_text,
            "limit": limit,
            "domainIds": _domain_ids(query),
        },
        operation="search",
    )
    results = data.get("searchKnowledges")
    if not isinstance(results, list):
        raise SystemError(
            "Knowledge engine did not return a searchKnowledges list"
        )

    # Project the KE list into the legacy KGE envelope
    # (``{results, total, page, limit}``) so existing clients that consume
    # ``inquire_catalog.payload`` verbatim keep working (T1.2).
    payload = {
        "results": results,
        "total": len(results),
        "page": query.get("page", 1),
        "limit": limit,
    }
    return _response(reference, payload)


def _node_inquiry(
    info: ResolveInfo,
    reference: CatalogReference,
    setting: dict,
    node_id: str,
) -> CatalogResponse:
    """Node-by-id lookup via KE ``knowledge(id)`` (lifts the KGE-era
    ``OperationUnsupportedError`` restriction — T1.3)."""
    data = _invoke_knowledge_engine(
        info,
        setting,
        _KE_KNOWLEDGE_QUERY,
        {"id": node_id},
        operation="knowledge",
    )
    payload = data.get("knowledge")
    if not isinstance(payload, dict):
        raise SystemError(
            "Knowledge engine did not return a knowledge payload for the node"
        )
    return _response(reference, payload)


def _ask_inquiry(
    info: ResolveInfo,
    reference: CatalogReference,
    setting: dict,
    query: dict[str, Any],
) -> CatalogResponse:
    """``ask`` mode — GraphRAG Q&A via KE ``askKnowledgeBase``."""
    question = query.get("query_text")
    if not question:
        raise SystemError("Catalog ask inquiry requires query.query_text")

    data = _invoke_knowledge_engine(
        info,
        setting,
        _KE_ASK_QUERY,
        {
            "question": question,
            "domainIds": _domain_ids(query),
            "maxHops": query.get("max_hops"),
            "topK": query.get("top_k"),
            "rerankTopK": query.get("rerank_top_k"),
            "sourceLevels": query.get("source_levels"),
        },
        operation="ask",
    )
    payload = data.get("askKnowledgeBase")
    if not isinstance(payload, dict):
        raise SystemError(
            "Knowledge engine did not return an askKnowledgeBase payload"
        )
    if not str(payload.get("answer") or "").strip():
        # KE may safely degrade a failed/unconfigured LLM to an empty answer.
        # Surface that failure through the RFQ in-band error contract instead
        # of presenting it as a successful catalog answer.
        raise SystemError(
            "Knowledge engine returned no answer; LLM answer generation "
            "is unavailable or failed"
        )
    return _response(reference, payload)


def _graph_inquiry(
    info: ResolveInfo,
    reference: CatalogReference,
    setting: dict,
    query: dict[str, Any],
) -> CatalogResponse:
    """``graph`` mode — graph visualization via KE ``knowledgeGraph``."""
    data = _invoke_knowledge_engine(
        info,
        setting,
        _KE_GRAPH_QUERY,
        {
            "domainIds": _domain_ids(query),
            "depth": query.get("depth", 2),
            "limit": query.get("limit", 100),
        },
        operation="graph",
    )
    payload = data.get("knowledgeGraph")
    if not isinstance(payload, dict):
        raise SystemError(
            "Knowledge engine did not return a knowledgeGraph payload"
        )
    return _response(reference, payload)


def _cypher_inquiry(
    info: ResolveInfo,
    reference: CatalogReference,
    setting: dict,
    query: dict[str, Any],
) -> CatalogResponse:
    """``cypher`` mode — raw Cypher via KE ``knowledgeGraphByCypher``.

    Accepts both the canonical ``retrieval_query`` argument name (kept from
    KGE for client compatibility) and ``cypher``.
    """
    cypher = query.get("retrieval_query") or query.get("cypher")
    if not cypher:
        raise SystemError("Catalog cypher inquiry requires query.retrieval_query")

    data = _invoke_knowledge_engine(
        info,
        setting,
        _KE_CYPHER_QUERY,
        {"cypher": cypher, "limit": query.get("limit")},
        operation="cypher",
    )
    payload = data.get("knowledgeGraphByCypher")
    if not isinstance(payload, dict):
        raise SystemError(
            "Knowledge engine did not return a knowledgeGraphByCypher payload"
        )
    return _response(reference, payload)


_MODE_ROUTER = {
    _MODE_SEARCH: _search_inquiry,
    _MODE_ASK: _ask_inquiry,
    _MODE_GRAPH: _graph_inquiry,
    _MODE_CYPHER: _cypher_inquiry,
}


# --------------------------------------------------------------------------- #
# Legacy KGE path (dual-run/rollback — removed at T4.3)
# --------------------------------------------------------------------------- #


def _legacy_kge_inquiry(
    info: ResolveInfo,
    reference: CatalogReference,
    setting: dict,
    query: dict[str, Any],
) -> CatalogResponse:
    """KGE ``search`` invocation (pre-migration read path)."""
    query_text = query.get("query_text")
    if not query_text:
        raise SystemError("Catalog browse inquiry requires query.query_text")

    if not (setting.get("functs_on_local") or {}).get("knowledge_graph_graphql"):
        raise SystemError(
            "functs_on_local.knowledge_graph_graphql must be configured to route "
            "catalog inquiries through Invoker.invoke_funct_on_local"
        )
    logger = info.context.get("logger") or logging.getLogger("catalog")

    # KGE was already initialized by the gateway with its own pg_table_prefix
    # (e.g. "kge_"). The Invoker re-initializes the target Config with the
    # setting dict, so we must ensure KGE's prefix is not overwritten by
    # RFQ's prefix. Use the per-module prefix from the setting dict.
    kge_setting = dict(setting)
    kge_setting["pg_table_prefix"] = setting.get("kge_pg_table_prefix", "")

    try:
        data = Invoker.invoke_funct_on_local(
            logger,
            kge_setting,
            "knowledge_graph_graphql",
            query=_KGE_SEARCH_QUERY,
            variables={
                "queryText": query_text,
                "searchMode": query.get("search_mode", "text2cypher"),
                "indexName": query.get("index_name", "vector"),
                "retrievalQuery": query.get("retrieval_query"),
                "filters": query.get("filters"),
                "topK": query.get("top_k", 10),
                "page": query.get("page", 1),
                "limit": query.get("limit", 10),
            },
            endpoint_id=info.context.get("endpoint_id"),
            part_id=info.context.get("part_id"),
        )
        if not isinstance(data, dict):
            raise SystemError("Knowledge graph invocation returned no data")
        payload = data.get("search")
        if not isinstance(payload, dict):
            raise SystemError(
                "Knowledge graph invocation did not return search payload"
            )
    except CatalogHandlerError:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "timeout" in message or "timed out" in message:
            raise SystemTimeoutError("Knowledge graph catalog search timed out") from exc
        raise SystemError(f"Knowledge graph catalog search failed: {exc}") from exc

    return _response(reference, payload)


# --------------------------------------------------------------------------- #
# Public dispatch boundary
# --------------------------------------------------------------------------- #


def dispatch_inquire(
    info: ResolveInfo,
    *,
    namespace: str = "DEFAULT",
    node_id: Optional[str] = None,
    query: Optional[Any] = None,
) -> CatalogResponse:
    """
    Inquire through the knowledge engine; KE owns all graph/tenant
    configuration (domains, types, extraction, vector stores).

    Routes by ``query.search_mode`` (default ``semantic``); ``node_id``
    performs a node-by-id lookup via KE ``knowledge(id)``.
    """
    from ..telemetry import measure_handler_duration

    with measure_handler_duration(
        info, operation="inquire", handler="catalog", namespace=namespace
    ):
        _partition_key(info)
        reference: CatalogReference = {
            "namespace": namespace,
            "node_id": node_id,
        }
        setting = Config.get_setting()

        if _backend(setting) == "kge":
            if node_id is not None:
                raise OperationUnsupportedError(
                    "Node inquiry is not enabled on the KGE backend: "
                    "knowledge_graph_engine does not expose a public "
                    "node-by-id query"
                )
            if not isinstance(query, dict):
                raise SystemError("Catalog browse inquiry requires a query object")
            return _legacy_kge_inquiry(info, reference, setting, query)

        if node_id is not None:
            return _node_inquiry(info, reference, setting, str(node_id))

        if not isinstance(query, dict):
            raise SystemError("Catalog inquiry requires a query object")

        search_mode = str(query.get("search_mode") or "semantic").strip().lower()
        engine_mode = _MODE_MAP.get(search_mode)
        if engine_mode is None:
            raise OperationUnsupportedError(
                f"Unsupported catalog inquiry search_mode: {search_mode!r} "
                "(supported: semantic, ask, graph, cypher)"
            )
        if search_mode not in _MODE_MAP or search_mode in (
            "text2cypher",
            "vector",
            "hybrid",
        ):
            logger = info.context.get("logger")
            if logger:
                logger.warning(
                    "catalog: legacy KGE search_mode %r mapped to KE mode %r",
                    search_mode,
                    engine_mode,
                )

        return _MODE_ROUTER[engine_mode](info, reference, setting, query)
