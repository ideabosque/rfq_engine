#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Unit tests for the knowledge_engine-backed catalog inquiry handler.

Covers the Phase 1 inquiry swap (KGE → KE):
mode routing (semantic default + ask/graph/cypher + legacy KGE mode
aliases), the KE payload envelope adapter, node-by-id inquiry, structured
``BIZ_KNOWLEDGE_*`` error mapping, the timeout string sniff fallback,
setting checks, the R4 setting isolation, and the legacy KGE dual-run
backend behind ``catalog_knowledge_backend: "kge"``.
"""
from __future__ import annotations

__author__ = "bibow"

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def info():
    return SimpleNamespace(
        context={
            "partition_key": "tenant-test",
            "endpoint_id": "gpt",
            "part_id": "test",
        }
    )


_KE_FUNCTS_ON_LOCAL_SETTING = {
    "functs_on_local": {
        "knowledge_engine_graphql": {
            "module_name": "knowledge_engine",
            "class_name": "KnowledgeEngine",
        },
    },
}

_KGE_FUNCTS_ON_LOCAL_SETTING = {
    "functs_on_local": {
        "knowledge_graph_graphql": {
            "module_name": "knowledge_graph_engine",
            "class_name": "KnowledgeGraphEngine",
        },
    },
    "kge_pg_table_prefix": "kge_",
}


# --- Default backend: knowledge_engine ------------------------------------- #


@pytest.mark.unit
def test_default_backend_is_knowledge_engine(info, monkeypatch):
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config,
        "get_setting",
        lambda: _KE_FUNCTS_ON_LOCAL_SETTING,
    )
    assert catalog_handler._backend(_KE_FUNCTS_ON_LOCAL_SETTING) == "knowledge_engine"


@pytest.mark.unit
def test_requires_knowledge_engine_funct(info, monkeypatch):
    from rfq_engine.handlers.catalog import (
        CatalogHandlerError,
        CatalogSystemError,
        ConfigurationError,
        dispatch_inquire,
    )
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: {"functs_on_local": {}}
    )
    # Unconfigured KE raises the structured ConfigurationError (T1.5),
    # which the resolver surfaces as errorCode="configuration_error".
    with pytest.raises(ConfigurationError, match="knowledge_engine_graphql"):
        dispatch_inquire(info, query={"query_text": "room"})
    assert ConfigurationError.code == "configuration_error"
    # ConfigurationError is still a CatalogHandlerError subclass.
    assert issubclass(ConfigurationError, CatalogHandlerError)
    assert issubclass(CatalogSystemError, CatalogHandlerError)


@pytest.mark.unit
def test_requires_partition_key():
    from rfq_engine.handlers.catalog import CatalogSystemError, dispatch_inquire

    with pytest.raises(CatalogSystemError, match="partition_key"):
        dispatch_inquire(SimpleNamespace(context={}), query={"query_text": "room"})


@pytest.mark.unit
def test_requires_query_object(info, monkeypatch):
    from rfq_engine.handlers.catalog import CatalogSystemError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    with pytest.raises(CatalogSystemError, match="query object"):
        dispatch_inquire(info, query=None)
    with pytest.raises(CatalogSystemError, match="query object"):
        dispatch_inquire(info, query="not-a-dict")


@pytest.mark.unit
def test_semantic_search_envelope_and_invocation(info, monkeypatch):
    """Default semantic mode calls searchKnowledges and projects the legacy
    ``{results, total, page, limit}`` envelope (T1.2)."""
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(
        return_value={
            "searchKnowledges": [
                {"id": "k1", "code": "item-u1", "name": "Onsen"},
                {"id": "k2", "code": "item-u2", "name": "Spa"},
            ]
        }
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    result = dispatch_inquire(
        info,
        query={
            "query_text": "onsen hotel",
            "search_mode": "semantic",
            "top_k": 5,
            "page": 1,
        },
    )

    args, kwargs = invoker_mock.call_args
    assert args[2] == "knowledge_engine_graphql"
    assert "searchKnowledges" in kwargs["query"]
    assert kwargs["variables"] == {"query": "onsen hotel", "limit": 5, "domainIds": None}
    assert kwargs["endpoint_id"] == "gpt"
    assert kwargs["part_id"] == "test"
    # Identity claims forwarded for KE access control.
    assert kwargs["context"]["partition_key"] == "tenant-test"

    payload = result["payload"]
    assert payload["total"] == 2
    assert payload["limit"] == 5
    assert payload["page"] == 1
    assert payload["results"][0]["id"] == "k1"
    assert result["ref"]["namespace"] == "DEFAULT"
    assert result["fetched_at"]


@pytest.mark.unit
def test_semantic_mode_is_default(info, monkeypatch):
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(return_value={"searchKnowledges": []})
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    dispatch_inquire(info, query={"query_text": "room"})

    assert "searchKnowledges" in invoker_mock.call_args[1]["query"]


@pytest.mark.unit
def test_search_limit_clamped_to_100(info, monkeypatch):
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(return_value={"searchKnowledges": []})
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    dispatch_inquire(info, query={"query_text": "x", "limit": 5000})
    assert invoker_mock.call_args[1]["variables"]["limit"] == 100


@pytest.mark.unit
def test_filters_domain_ids_mapped(info, monkeypatch):
    """Legacy KGE ``filters.domain_ids`` maps to KE ``domainIds``."""
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(return_value={"searchKnowledges": []})
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    dispatch_inquire(
        info,
        query={
            "query_text": "x",
            "filters": {"domain_ids": ["d-1", "d-2"]},
        },
    )
    assert invoker_mock.call_args[1]["variables"]["domainIds"] == ["d-1", "d-2"]


# --- Node inquiry (T1.3) ---------------------------------------------------- #


@pytest.mark.unit
def test_node_id_inquiry_supported(info, monkeypatch):
    """node_id lookup now routes to KE ``knowledge(id)`` — the KGE-era
    OperationUnsupportedError restriction is lifted."""
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(
        return_value={
            "knowledge": {
                "id": "k-123",
                "code": "item-u1",
                "name": "Onsen",
                "status": "PUBLISHED",
                "content": "...",
            }
        }
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    result = dispatch_inquire(info, namespace="hotel", node_id="k-123")

    kwargs = invoker_mock.call_args[1]
    assert "knowledge(id: $id)" in kwargs["query"]
    assert kwargs["variables"] == {"id": "k-123"}
    assert result["ref"] == {"namespace": "hotel", "node_id": "k-123"}
    assert result["payload"]["id"] == "k-123"
    assert result["payload"]["status"] == "PUBLISHED"


# --- Mode routing (T1.4) ---------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("answer", ["", "   ", None])
def test_empty_llm_answer_is_an_explicit_failure(info, monkeypatch, answer):
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler

    monkeypatch.setattr(handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING)
    monkeypatch.setattr(handler.Invoker, "invoke_funct_on_local", MagicMock(
        return_value={"askKnowledgeBase": {"answer": answer, "usage": {"retrieval_status": "NO_MATCH"}}}
    ))
    with pytest.raises(handler.SystemError, match="LLM answer generation"):
        dispatch_inquire(info, query={"query_text": "flight", "search_mode": "ask"})


@pytest.mark.unit
def test_ask_mode(info, monkeypatch):
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(
        return_value={"askKnowledgeBase": {"answer": "42", "confidence": 0.9}}
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    result = dispatch_inquire(
        info,
        query={
            "query_text": "cheapest onsen?",
            "search_mode": "ask",
            "max_hops": 3,
            "top_k": 8,
        },
    )

    kwargs = invoker_mock.call_args[1]
    assert "askKnowledgeBase" in kwargs["query"]
    assert kwargs["variables"]["question"] == "cheapest onsen?"
    assert kwargs["variables"]["maxHops"] == 3
    assert kwargs["variables"]["topK"] == 8
    assert result["payload"]["answer"] == "42"


@pytest.mark.unit
def test_graph_mode(info, monkeypatch):
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(
        return_value={
            "knowledgeGraph": {"nodes": [], "edges": [], "totalNodes": 0, "totalEdges": 0}
        }
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    result = dispatch_inquire(
        info, query={"search_mode": "graph", "depth": 3, "limit": 50}
    )

    kwargs = invoker_mock.call_args[1]
    assert "knowledgeGraph(" in kwargs["query"]
    assert kwargs["variables"]["depth"] == 3
    assert kwargs["variables"]["limit"] == 50
    assert result["payload"]["totalNodes"] == 0


@pytest.mark.unit
def test_cypher_mode_accepts_retrieval_query_alias(info, monkeypatch):
    """``retrieval_query`` (KGE-era arg) maps to KE ``cypher``."""
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    invoker_mock = MagicMock(
        return_value={
            "knowledgeGraphByCypher": {
                "nodes": [{"id": "n1"}],
                "edges": [],
                "totalNodes": 1,
                "totalEdges": 0,
            }
        }
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    result = dispatch_inquire(
        info,
        query={
            "search_mode": "cypher",
            "retrieval_query": "MATCH (n:Entity) RETURN n LIMIT 10",
            "limit": 10,
        },
    )

    kwargs = invoker_mock.call_args[1]
    assert "knowledgeGraphByCypher" in kwargs["query"]
    assert kwargs["variables"]["cypher"] == "MATCH (n:Entity) RETURN n LIMIT 10"
    assert result["payload"]["totalNodes"] == 1


@pytest.mark.unit
def test_legacy_kge_mode_aliases_route_and_log(info, monkeypatch):
    """text2cypher → cypher; vector/hybrid → semantic (logged)."""
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    logger = MagicMock()
    info.context["logger"] = logger
    invoker_mock = MagicMock(
        return_value={
            "knowledgeGraphByCypher": {"nodes": [], "edges": [], "totalNodes": 0, "totalEdges": 0}
        }
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    dispatch_inquire(
        info,
        query={"search_mode": "text2cypher", "retrieval_query": "MATCH (n) RETURN n"},
    )
    assert "knowledgeGraphByCypher" in invoker_mock.call_args[1]["query"]
    logger.warning.assert_called_once()

    invoker_mock.reset_mock()
    invoker_mock.return_value = {"searchKnowledges": []}
    dispatch_inquire(info, query={"query_text": "x", "search_mode": "vector"})
    assert "searchKnowledges" in invoker_mock.call_args[1]["query"]

    invoker_mock.reset_mock()
    dispatch_inquire(info, query={"query_text": "x", "search_mode": "hybrid"})
    assert "searchKnowledges" in invoker_mock.call_args[1]["query"]


@pytest.mark.unit
def test_unknown_mode_is_operation_unsupported(info, monkeypatch):
    from rfq_engine.handlers.catalog import OperationUnsupportedError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    with pytest.raises(OperationUnsupportedError, match="search_mode"):
        dispatch_inquire(info, query={"query_text": "x", "search_mode": "quantum"})


# --- Error mapping (T1.5) --------------------------------------------------- #


@pytest.mark.unit
def test_biz_timeout_maps_to_system_timeout(info, monkeypatch):
    from rfq_engine.handlers.catalog import SystemTimeoutError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    monkeypatch.setattr(
        catalog_handler.Invoker,
        "invoke_funct_on_local",
        MagicMock(side_effect=Exception([{"message": "BIZ_KNOWLEDGE_TIMEOUT: llm took too long"}])),
    )
    with pytest.raises(SystemTimeoutError):
        dispatch_inquire(info, query={"query_text": "x"})


@pytest.mark.unit
def test_timeout_string_sniff_fallback(info, monkeypatch):
    from rfq_engine.handlers.catalog import SystemTimeoutError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    monkeypatch.setattr(
        catalog_handler.Invoker,
        "invoke_funct_on_local",
        MagicMock(side_effect=Exception("Connection to neo4j timed out")),
    )
    with pytest.raises(SystemTimeoutError):
        dispatch_inquire(info, query={"query_text": "x"})


@pytest.mark.unit
def test_biz_not_found_maps_to_not_found(info, monkeypatch):
    from rfq_engine.handlers.catalog import NotFoundError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    monkeypatch.setattr(
        catalog_handler.Invoker,
        "invoke_funct_on_local",
        MagicMock(
            side_effect=Exception(
                [{"message": "BIZ_KNOWLEDGE_NOT_FOUND: id k-404 missing"}]
            )
        ),
    )
    with pytest.raises(NotFoundError):
        dispatch_inquire(info, node_id="k-404")


@pytest.mark.unit
def test_biz_access_denied_maps_to_access_denied(info, monkeypatch):
    from rfq_engine.handlers.catalog import AccessDeniedError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    monkeypatch.setattr(
        catalog_handler.Invoker,
        "invoke_funct_on_local",
        MagicMock(
            side_effect=Exception(
                [{"message": "BIZ_KNOWLEDGE_ACCESS_DENIED: platform scope required"}]
            )
        ),
    )
    with pytest.raises(AccessDeniedError):
        dispatch_inquire(info, query={"search_mode": "graph"})


@pytest.mark.unit
def test_other_engine_errors_map_to_system_error(info, monkeypatch):
    from rfq_engine.handlers.catalog import CatalogSystemError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    monkeypatch.setattr(
        catalog_handler.Config, "get_setting", lambda: _KE_FUNCTS_ON_LOCAL_SETTING
    )
    monkeypatch.setattr(
        catalog_handler.Invoker,
        "invoke_funct_on_local",
        MagicMock(
            side_effect=Exception(
                [{"message": "BIZ_KNOWLEDGE_VALIDATION: bad type_id"}]
            )
        ),
    )
    with pytest.raises(CatalogSystemError, match="BIZ_KNOWLEDGE_VALIDATION"):
        dispatch_inquire(info, query={"query_text": "x"})


# --- R4: setting isolation -------------------------------------------------- #


@pytest.mark.unit
def test_ke_setting_strips_rfq_backend_keys_and_applies_overrides():
    from rfq_engine.handlers.catalog import handler as catalog_handler

    setting = {
        "db_backend": "postgresql",
        "initialize_tables": True,
        "pg_table_prefix": "rfq_",
        "functs_on_local": {"knowledge_engine_graphql": {}},
        "knowledge_engine_setting": {"llm": {"provider": "openai"}},
    }
    ke_setting = catalog_handler._ke_setting(setting)
    assert "db_backend" not in ke_setting
    assert "initialize_tables" not in ke_setting
    assert "pg_table_prefix" not in ke_setting
    assert ke_setting["functs_on_local"] == {"knowledge_engine_graphql": {}}
    assert ke_setting["llm"] == {"provider": "openai"}


@pytest.mark.unit
def test_ke_context_forwards_identity_claims(info):
    from rfq_engine.handlers.catalog import handler as catalog_handler

    info.context.update(
        {
            "user": {"sub": "user-1"},
            "tenant_id": "t-9",
            "roles": ["r1"],
            "permissions": ["knowledge:read"],
        }
    )
    context = catalog_handler._ke_context(info)
    assert context["partition_key"] == "tenant-test"
    assert context["tenant_id"] == "t-9"
    assert context["roles"] == ["r1"]
    assert context["permissions"] == ["knowledge:read"]
    assert context["user"] == {"sub": "user-1"}


# --- Legacy KGE dual-run backend (T4.1 rollback path) ----------------------- #


@pytest.mark.unit
def test_kge_backend_flag_routes_to_legacy_search(info, monkeypatch):
    from rfq_engine.handlers.catalog import dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    setting = dict(_KGE_FUNCTS_ON_LOCAL_SETTING)
    setting["catalog_knowledge_backend"] = "kge"
    monkeypatch.setattr(catalog_handler.Config, "get_setting", lambda: setting)
    invoker_mock = MagicMock(
        return_value={"search": {"results": [{"name": "Onsen"}], "total": 1}}
    )
    monkeypatch.setattr(catalog_handler.Invoker, "invoke_funct_on_local", invoker_mock)

    result = dispatch_inquire(info, query={"query_text": "onsen hotel"})

    args, kwargs = invoker_mock.call_args
    assert args[2] == "knowledge_graph_graphql"
    assert kwargs["variables"]["queryText"] == "onsen hotel"
    # KGE pg_table_prefix preserved against Invoker Config re-init (R4).
    assert args[1]["pg_table_prefix"] == "kge_"
    assert result["payload"]["total"] == 1


@pytest.mark.unit
def test_kge_backend_still_rejects_node_lookup(info, monkeypatch):
    from rfq_engine.handlers.catalog import OperationUnsupportedError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    setting = dict(_KGE_FUNCTS_ON_LOCAL_SETTING)
    setting["catalog_knowledge_backend"] = "kge"
    monkeypatch.setattr(catalog_handler.Config, "get_setting", lambda: setting)

    with pytest.raises(OperationUnsupportedError, match="node-by-id"):
        dispatch_inquire(info, namespace="hotel", node_id="room-1")


@pytest.mark.unit
def test_kge_backend_requires_kge_funct(info, monkeypatch):
    from rfq_engine.handlers.catalog import CatalogSystemError, dispatch_inquire
    from rfq_engine.handlers.catalog import handler as catalog_handler

    setting = {"catalog_knowledge_backend": "kge", "functs_on_local": {}}
    monkeypatch.setattr(catalog_handler.Config, "get_setting", lambda: setting)

    with pytest.raises(CatalogSystemError, match="knowledge_graph_graphql"):
        dispatch_inquire(info, query={"query_text": "room"})


# --- Resolver in-band contract (C4/C5) --------------------------------------- #


@pytest.mark.unit
def test_graphql_wrapper_returns_structured_catalog_error(info, monkeypatch):
    from rfq_engine.handlers.catalog import CatalogSystemError
    from rfq_engine.queries import catalog_inquiry

    monkeypatch.setattr(
        catalog_inquiry,
        "dispatch_inquire",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CatalogSystemError("KE unavailable")
        ),
    )
    result = catalog_inquiry.resolve_inquire_catalog(info, node_id="room-1")
    assert result.error_code == "system_error"
    assert result.payload is None


@pytest.mark.unit
def test_graphql_wrapper_returns_structured_configuration_error(info, monkeypatch):
    from rfq_engine.handlers.catalog import ConfigurationError
    from rfq_engine.queries import catalog_inquiry

    monkeypatch.setattr(
        catalog_inquiry,
        "dispatch_inquire",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ConfigurationError("functs_on_local.knowledge_engine_graphql missing")
        ),
    )
    result = catalog_inquiry.resolve_inquire_catalog(info, query={"query_text": "x"})
    assert result.error_code == "configuration_error"
    assert result.payload is None
    assert "knowledge_engine_graphql" in result.error_message


@pytest.mark.unit
def test_graphql_wrapper_returns_payload_on_success(info, monkeypatch):
    from rfq_engine.queries import catalog_inquiry

    monkeypatch.setattr(
        catalog_inquiry,
        "dispatch_inquire",
        lambda *args, **kwargs: {
            "ref": {"namespace": "FLIGHTS", "node_id": None},
            "payload": {"results": [], "total": 0},
            "fetched_at": "2026-10-19T18:00:00Z",
            "ttl_seconds": None,
        },
    )
    result = catalog_inquiry.resolve_inquire_catalog(
        info, query={"query_text": "x"}
    )
    assert result.error_code is None
    assert result.namespace == "FLIGHTS"
    assert result.payload["total"] == 0
    assert result.fetched_at is not None
