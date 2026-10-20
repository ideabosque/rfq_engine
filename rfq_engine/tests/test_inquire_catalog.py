#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Integration tests for ``resolve_inquire_catalog`` (schema.py:resolve_inquire_catalog
-> queries/catalog_inquiry.resolve_inquire_catalog -> handlers/catalog/handler.dispatch_inquire).

The resolver wraps the knowledge_engine-backed catalog handler, which routes
in-process through ``Invoker.invoke_funct_on_local`` to
``knowledge_engine.knowledge_engine_graphql``. These tests require:

  * RFQ Engine reachable (DB credentials + base_dir set in tests/.env)
  * knowledge_engine importable on sys.path and initialized (gateway mount,
    Phase 0 T0.1) with LLM/embedding/Neo4j config groups for the partition
  * KE content present (run the ingestion bridge or KE seed data first so
    the "queryable hits" tests find something)

Covered scenarios:

  1. Happy path — semantic query returns the legacy ``{results, total}``
     payload envelope from KE ``searchKnowledges``.
  2. Node-by-id inquiry via ``nodeId`` succeeds against KE ``knowledge(id)``
     (restriction lifted — INT-019).
  3. Missing/invalid query payload surfaces ``errorCode="system_error"``
     without raising a GraphQL transport error.
  4. ask/graph/cypher modes route to their KE operations.
  5. Write→read loop — ``ingestKnowledgeFromRfq`` then
     ``inquireCatalog(nodeId)`` resolves end-to-end when ingestion settings
     are provisioned.
"""
from __future__ import annotations

__author__ = "bibow"

import json
import logging
import os
import sys
from typing import Any, Dict

import pytest
from silvaengine_utility.serializer import Serializer

logger = logging.getLogger("test_inquire_catalog")

SETTING = {
    "region_name": os.getenv("region_name"),
    "aws_access_key_id": os.getenv("aws_access_key_id"),
    "aws_secret_access_key": os.getenv("aws_secret_access_key"),
    "functs_on_local": {
        "ai_rfq_graphql": {
            "module_name": "rfq_engine",
            "class_name": "RFQEngine",
        },
        "knowledge_engine_graphql": {
            "module_name": "knowledge_engine",
            "class_name": "KnowledgeEngine",
        },
    },
    "endpoint_id": os.getenv("endpoint_id"),
    "part_id": os.getenv("part_id"),
    "execute_mode": os.getenv("execute_mode", "local"),
    "initialize_tables": os.getenv("initialize_tables", "0") == "1",
    "cache_enabled": os.getenv("cache_enabled", "0") == "1",
    # Phase 0 T0.2 provisioning (recorded per tenant):
    "knowledge_engine_ingest": {
        "domain_id": os.getenv("ke_domain_id"),
        "type_ids": {
            "item": os.getenv("ke_type_item"),
        },
        "namespace": os.getenv("ke_ingest_namespace", "KE"),
        "sync_item_catalog_ref": os.getenv("ke_sync_refs", "1") == "1",
    },
}

BASE_DIR = os.getenv("base_dir") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "silvaengine_utility"))
sys.path.insert(1, os.path.join(BASE_DIR, "silvaengine_dynamodb_base"))
sys.path.insert(2, BASE_DIR if "rfq_engine" in BASE_DIR else os.path.join(BASE_DIR, "rfq_engine"))
sys.path.insert(3, os.getenv("ke_base_dir") or os.path.join(BASE_DIR, "knowledge_engine"))

try:
    from rfq_engine import RFQEngine
except ImportError:
    RFQEngine = None


# --- Fixtures -------------------------------------------------------------- #


@pytest.fixture(scope="module")
def engine():
    if RFQEngine is None:
        pytest.skip("RFQEngine not importable")
    if not SETTING.get("endpoint_id") or not SETTING.get("part_id"):
        pytest.skip("endpoint_id / part_id missing from tests/.env")
    try:
        import knowledge_engine  # noqa: F401

        from knowledge_engine.handlers.config import Config as KEConfig

        if not KEConfig._initialized:
            pytest.skip(
                "knowledge_engine not initialized (gateway mount / Phase 0 T0.1)"
            )
    except Exception:
        pytest.skip("knowledge_engine not importable on sys.path")
    try:
        e = RFQEngine(logger, **SETTING)
        setattr(e, "__is_real__", True)
        return e
    except Exception as exc:
        pytest.skip(f"Engine init failed: {exc}")


@pytest.fixture(scope="module")
def endpoint_id():
    return SETTING.get("endpoint_id")


@pytest.fixture(scope="module")
def part_id():
    return SETTING.get("part_id")


@pytest.fixture(scope="module")
def ingest_ready():
    ingest = SETTING.get("knowledge_engine_ingest") or {}
    if not ingest.get("domain_id") or not ingest.get("type_ids", {}).get("item"):
        pytest.skip("ke_domain_id / ke_type_item not set in tests/.env (T0.2)")
    return ingest


# --- GraphQL helper -------------------------------------------------------- #


_INQUIRE_CATALOG_QUERY = """
query InquireCatalog($namespace: String, $nodeId: String, $query: JSONCamelCase) {
    inquireCatalog(namespace: $namespace, nodeId: $nodeId, query: $query) {
        namespace
        nodeId
        payload
        fetchedAt
        ttlSeconds
        errorCode
        errorMessage
    }
}
"""

_INGEST_KNOWLEDGE_MUTATION = """
mutation IngestKnowledgeFromRfq(
    $entityType: String!,
    $uuid: String!
) {
    ingestKnowledgeFromRfq(entityType: $entityType, uuid: $uuid) {
        result {
            status
            entityType
            entityUuid
            knowledgeId
            errorCode
            errorMessage
        }
    }
}
"""


def _graphql(
    engine,
    query: str,
    variables: Dict[str, Any],
    endpoint_id: str,
    part_id: str,
) -> Dict[str, Any]:
    response = engine.rfq_graphql(
        query=query,
        variables=variables,
        endpoint_id=endpoint_id,
        part_id=part_id,
    )
    parsed = (
        Serializer.json_loads(response)
        if isinstance(response, (str, bytes))
        else response
    )
    if isinstance(parsed, dict) and isinstance(parsed.get("body"), str):
        try:
            parsed = Serializer.json_loads(parsed["body"])
        except Exception:
            pass
    if isinstance(parsed, dict) and parsed.get("errors"):
        raise RuntimeError(f"GraphQL errors: {parsed['errors']}")
    data = parsed.get("data", parsed) if isinstance(parsed, dict) else {}
    return data


def _inquire(engine, variables, endpoint_id, part_id) -> Dict[str, Any]:
    return _graphql(
        engine, _INQUIRE_CATALOG_QUERY, variables, endpoint_id, part_id
    ).get("inquireCatalog") or {}


# --- Tests ----------------------------------------------------------------- #


class TestInquireCatalog:
    """Integration coverage for the KE-backed inquire_catalog resolver."""

    @pytest.mark.integration
    def test_semantic_query_returns_legacy_envelope(
        self, engine, endpoint_id, part_id
    ):
        """Default semantic mode hits KE searchKnowledges and returns the
        ``{results, total, page, limit}`` envelope."""
        print("\n=== test_semantic_query_returns_legacy_envelope ===", flush=True)
        result = _inquire(
            engine,
            {
                "namespace": "KE",
                "query": {
                    "queryText": "onsen",
                    "searchMode": "semantic",
                    "limit": 5,
                },
            },
            endpoint_id,
            part_id,
        )
        print(
            f"errorCode={result.get('errorCode')!r} "
            f"errorMessage={result.get('errorMessage')!r}",
            flush=True,
        )
        assert result.get("errorCode") is None, result
        payload = result.get("payload") or {}
        assert isinstance(payload, dict), f"payload should be a dict, got {payload!r}"
        assert "results" in payload, f"payload missing 'results': keys={list(payload)}"
        assert isinstance(payload["results"], list)
        assert payload["total"] == len(payload["results"])
        print(
            f"PASS -- {payload['total']} result(s) returned in legacy envelope",
            flush=True,
        )

    @pytest.mark.integration
    def test_missing_query_text_returns_system_error(
        self, engine, endpoint_id, part_id
    ):
        """A browse inquiry without ``queryText`` must not raise — the
        handler converts it to in-band ``errorCode="system_error"``."""
        print("\n=== test_missing_query_text_returns_system_error ===", flush=True)
        result = _inquire(
            engine,
            {"query": {"searchMode": "semantic"}},  # missing queryText
            endpoint_id,
            part_id,
        )
        assert result.get("errorCode") == "system_error", result
        print("PASS -- missing queryText surfaced as system_error", flush=True)

    @pytest.mark.integration
    def test_unknown_mode_returns_operation_unsupported(
        self, engine, endpoint_id, part_id
    ):
        result = _inquire(
            engine,
            {"query": {"queryText": "x", "searchMode": "quantum"}},
            endpoint_id,
            part_id,
        )
        assert result.get("errorCode") == "operation_unsupported", result

    @pytest.mark.integration
    def test_ask_graph_cypher_modes_route(
        self, engine, endpoint_id, part_id
    ):
        """ask/graph/cypher route to their KE operations; graph/cypher may
        legitimately fail-closed on access (INT-021) but must stay in-band."""
        for mode in ("ask", "graph", "cypher"):
            query: Dict[str, Any] = {"queryText": "onsen", "searchMode": mode}
            if mode == "cypher":
                query["retrievalQuery"] = "MATCH (n:Entity) RETURN n LIMIT 5"
            result = _inquire(
                engine, {"query": query}, endpoint_id, part_id
            )
            assert result.get("errorCode") in (
                None,
                "access_denied",
                "system_error",
            ), result
            print(
                f"mode={mode} -> errorCode={result.get('errorCode')!r}",
                flush=True,
            )

    @pytest.mark.integration
    def test_write_read_loop_via_node_inquiry(
        self, engine, endpoint_id, part_id, ingest_ready
    ):
        """T2.7/DoD-3: ingest an RFQ entity then resolve it through
        ``inquireCatalog(nodeId)`` — the write→read loop closes with
        ``node_id`` = KE knowledge id."""
        print("\n=== test_write_read_loop_via_node_inquiry ===", flush=True)
        ingest = (
            _graphql(
                engine,
                _INGEST_KNOWLEDGE_MUTATION,
                {"entityType": "item", "uuid": "u-item-1"},
                endpoint_id,
                part_id,
            ).get("ingestKnowledgeFromRfq")
            or {}
        ).get("result") or {}
        status = ingest.get("status")
        print(
            f"ingest status={status!r} error={ingest.get('errorMessage')!r}",
            flush=True,
        )
        assert status == "ok", ingest
        knowledge_id = ingest.get("knowledgeId")
        assert knowledge_id

        result = _inquire(
            engine, {"namespace": "KE", "nodeId": knowledge_id}, endpoint_id, part_id
        )
        assert result.get("errorCode") is None, result
        payload = result.get("payload") or {}
        assert payload.get("id") == str(knowledge_id)
        assert payload.get("code") == "item-u-item-1"
        print(
            f"PASS -- nodeId {knowledge_id} resolved end-to-end",
            flush=True,
        )


if __name__ == "__main__":
    # Make `python test_inquire_catalog.py` work the same as
    # `pytest test_inquire_catalog.py -v -s`.
    import sys as _sys

    _sys.exit(
        pytest.main(
            [
                __file__,
                "-v",
                "-s",
                "--log-cli-level=INFO",
                *_sys.argv[1:],
            ]
        )
    )