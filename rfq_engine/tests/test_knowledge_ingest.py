#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Unit tests for the RFQ → knowledge_engine ingestion bridge (Phase 2).

Covers: settings fail-fast (R2), entity fetch + markdown projection (D1),
deterministic idempotency keys (T2.4), upsert-by-code semantics
(create/update/no-op replay/version-conflict retry), batch accounting with
per-item attribution (T2.5), file ingestion transports (D2), the
ItemCatalogRef auto-sync (T2.7), and KE error mapping (T1.5).

All KE interactions are mocked through ``Invoker.invoke_funct_on_local``;
no live knowledge engine or database is required.
"""
from __future__ import annotations

__author__ = "bibow"

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from rfq_engine.handlers.catalog import ingest as catalog_ingest
from rfq_engine.handlers.catalog.ingest import (
    STATUS_ACCESS_DENIED,
    STATUS_CONFIGURATION_ERROR,
    STATUS_ERROR,
    STATUS_NOT_FOUND,
    STATUS_NOT_SUPPORTED,
    STATUS_OK,
    STATUS_TIMEOUT,
    _derive_idempotency_key,
    _project_markdown,
)


@pytest.fixture
def info():
    return SimpleNamespace(
        context={
            "partition_key": "tenant-test",
            "endpoint_id": "gpt",
            "part_id": "test",
        }
    )


_SETTING = {
    "functs_on_local": {
        "knowledge_engine_graphql": {
            "module_name": "knowledge_engine",
            "class_name": "KnowledgeEngine",
        },
    },
    "knowledge_engine_ingest": {
        "domain_id": "domain-rfq",
        "type_ids": {
            "item": "type-item",
            "provider_item": "type-provider-item",
            "request": "type-request",
            "quote": "type-quote",
            "bundle": "type-bundle",
            "discount_prompt": "type-discount-prompt",
        },
        "namespace": "KE",
        "max_concurrent_ingests": 4,
    },
}


_ITEM_ROW = {
    "item_uuid": "u-item-1",
    "item_type": "onsen",
    "item_name": "Hakone Onsen Day Pass",
    "item_description": "Full-day onsen access with mountain view.",
    "pricing_mode": "per_uom",
    "uom": "person",
    "item_external_id": "ONS-DAY",
    "updated_at": "2026-10-01T00:00:00Z",
}


@pytest.mark.parametrize("identifiers,expected", [
    ({"knowledge_id": "knowledge-1"}, "metadata_stored"),
    ({"source_id": "source-1"}, "import_submitted"),
])
def test_success_reports_completed_processing_stage(identifiers, expected):
    result = catalog_ingest._result(status=STATUS_OK, **identifiers)
    assert result["processing_stage"] == expected


def test_failure_does_not_claim_completed_processing():
    result = catalog_ingest._result(status=STATUS_TIMEOUT, knowledge_id="knowledge-1")
    assert result["processing_stage"] is None

_PROVIDER_ITEM_ROW = {
    "provider_item_uuid": "u-pi-1",
    "item_uuid": "u-item-1",
    "provider_corp_external_id": "corp-7",
    "provider_item_external_id": "ONS-DAY-7",
    "base_price_per_uom": 120.0,
    "availability_mode": "batch",
    "item_spec": {"supplier_name": "Hakone Kanko", "cabin_class": "open-air"},
    "updated_at": "2026-10-02T00:00:00Z",
}

_QUOTE_ROW = {
    "quote_uuid": "u-quote-1",
    "request_uuid": "u-req-1",
    "provider_corp_external_id": "corp-7",
    "status": "draft",
    "total_quote_amount": 240.0,
    "currency": "USD",
    "updated_at": "2026-10-03T00:00:00Z",
}


class _FakeRepo:
    """EntityRepository double: rows keyed by uuid."""

    def __init__(self, rows: Dict[str, dict], name: str):
        self._rows = rows
        self.name = name
        self.insert_update_calls: List[Dict[str, Any]] = []
        self.list_rows: List[dict] = []

    def get(self, **keys):
        if self.name == "file":
            return self._rows.get((keys.get("request_uuid"), keys.get("file_name")))
        uuid_key = {
            "item": "item_uuid",
            "provider_item": "provider_item_uuid",
            "request": "request_uuid",
            "quote": "quote_uuid",
            "bundle": "bundle_uuid",
            "discount_prompt": "discount_prompt_uuid",
            "item_catalog_ref": "catalog_ref_uuid",
        }.get(self.name, "uuid")
        uuid = keys.get(uuid_key) or keys.get("uuid")
        if self.name == "quote":
            if keys.get("request_uuid") != next(iter(self._rows.values()), {}).get(
                "request_uuid"
            ):
                return None
        return self._rows.get(uuid)

    def list(self, info, **filters):
        listing = MagicMock()
        listing.provider_item_list = [
            SimpleNamespace(provider_item_uuid=pid) for pid in self._list_ids()
        ]
        return listing

    def _list_ids(self):
        return [r.get("provider_item_uuid") for r in self.list_rows]

    def insert_update(self, info, **kwargs):
        self.insert_update_calls.append(kwargs)
        return kwargs


class _FakeInvoker:
    """
    State-aware KE double: records GraphQL documents/variables and serves
    scripted responses per operation (knowledges_by_code / createKnowledge /
    updateKnowledge / importKnowledge / importKnowledgeFromUrl).
    """

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.knowledge_by_code: Dict[str, dict] = {}
        self.fail_next: Optional[Dict[str, Exception]] = {}
        self.failures: Dict[str, List[Exception]] = {}
        self.created: List[dict] = []
        self.updated: List[dict] = []
        # Optional scripted lookup sequence (popped per knowledges call);
        # entries of None mean "not found". Exhausted -> knowledge_by_code.
        self.lookup_script: List[Optional[dict]] = []

    def _scripted_failure(self, operation: str) -> Optional[Exception]:
        failures = self.failures.get(operation) or []
        if failures:
            return failures.pop(0)
        return None

    def __call__(self, logger, setting, funct, **params):
        query = params.get("query") or ""
        if "knowledges(" in query:
            op = "knowledges"
        elif "createKnowledge" in query:
            op = "createKnowledge"
        elif "updateKnowledge" in query:
            op = "updateKnowledge"
        elif "importKnowledgeFromUrl" in query:
            op = "importKnowledgeFromUrl"
        elif "importKnowledge" in query:
            op = "importKnowledge"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unexpected query: {query[:120]}")
        self.calls.append({"op": op, "params": params})

        failure = self._scripted_failure(op)
        if failure is not None:
            raise failure

        if op == "knowledges":
            code = params["variables"]["filter"]["code"]
            node: Optional[dict]
            if self.lookup_script:
                node = self.lookup_script.pop(0)
            else:
                node = self.knowledge_by_code.get(code)
            return {
                "knowledges": {
                    "edges": [{"node": node}] if node else [],
                    "totalCount": 1 if node else 0,
                }
            }
        if op == "createKnowledge":
            variables = params["variables"]
            node = {
                "id": f"ke-{len(self.created) + 1}",
                "code": variables["input"]["code"],
                "name": variables["input"]["name"],
                "typeId": variables["input"]["typeId"],
                "domainId": variables["input"]["domainId"],
                "status": "DRAFT",
                "content": variables["input"].get("content"),
                "updatedAt": "2026-10-19T00:00:00Z",
            }
            self.created.append(variables["input"])
            self.knowledge_by_code[node["code"]] = node
            return {"createKnowledge": node}
        if op == "updateKnowledge":
            variables = params["variables"]
            # Update the node found by id.
            for code, candidate in self.knowledge_by_code.items():
                if candidate["id"] == str(variables["id"]):
                    candidate = dict(candidate)
                    candidate.update(
                        {
                            "name": variables["input"].get("name")
                            or candidate.get("name"),
                            "content": variables["input"].get("content"),
                            "status": candidate.get("status", "DRAFT"),
                            "updatedAt": "2026-10-19T01:00:00Z",
                        }
                    )
                    self.knowledge_by_code[code] = candidate
                    self.updated.append(variables["input"])
                    return {"updateKnowledge": candidate}
            raise Exception("node not found in fake KE")
        if op in ("importKnowledge", "importKnowledgeFromUrl"):
            return {
                op: {
                    "sourceId": "src-1",
                    "filename": "spec.pdf",
                    "size": 10,
                    "format": "URL" if op.endswith("FromUrl") else "application/pdf",
                    "status": "COMPLETED",
                    "createdAt": "2026-10-19T00:00:00Z",
                }
            }
        raise AssertionError(op)


@pytest.fixture
def invoker(monkeypatch):
    fake = _FakeInvoker()
    monkeypatch.setattr(catalog_ingest.Invoker, "invoke_funct_on_local", fake)
    return fake


@pytest.fixture
def repos(monkeypatch):
    catalog_repo = _FakeRepo({}, "item_catalog_ref")
    registry = {
        "item": _FakeRepo({"u-item-1": dict(_ITEM_ROW)}, "item"),
        "provider_item": _FakeRepo({"u-pi-1": dict(_PROVIDER_ITEM_ROW)}, "provider_item"),
        "request": _FakeRepo({"u-req-1": {"request_uuid": "u-req-1"}}, "request"),
        "quote": _FakeRepo({"u-quote-1": dict(_QUOTE_ROW)}, "quote"),
        "bundle": _FakeRepo({"u-bundle-1": {"bundle_uuid": "u-bundle-1"}}, "bundle"),
        "discount_prompt": _FakeRepo({}, "discount_prompt"),
        "file": _FakeRepo(
            {("u-req-1", "spec.pdf"): {"request_uuid": "u-req-1", "file_name": "spec.pdf", "updated_at": "2026-10-01T00:00:00Z"}},
            "file",
        ),
        "item_catalog_ref": catalog_repo,
    }
    monkeypatch.setattr(catalog_ingest, "get_repo", lambda name: registry[name])
    return registry


@pytest.fixture
def setting(monkeypatch):
    monkeypatch.setattr(catalog_ingest.Config, "get_setting", lambda: _SETTING)
    return _SETTING


# --- Pure helpers ----------------------------------------------------------- #


@pytest.mark.unit
def test_idempotency_key_is_deterministic_and_content_sensitive():
    key_1 = _derive_idempotency_key(
        "gpt#test", "item", "u-1", "2026-10-01T00:00:00Z", "content-a"
    )
    key_2 = _derive_idempotency_key(
        "gpt#test", "item", "u-1", "2026-10-01T00:00:00Z", "content-a"
    )
    key_changed_content = _derive_idempotency_key(
        "gpt#test", "item", "u-1", "2026-10-01T00:00:00Z", "content-b"
    )
    key_changed_updated_at = _derive_idempotency_key(
        "gpt#test", "item", "u-1", "2026-10-02T00:00:00Z", "content-a"
    )
    assert key_1 == key_2
    assert key_1.startswith("rfq:gpt#test:item:u-1:")
    assert key_1 != key_changed_content
    assert key_1 != key_changed_updated_at


@pytest.mark.unit
def test_markdown_projection_item():
    markdown = _project_markdown("item", dict(_ITEM_ROW))
    assert markdown.startswith("# Item: Hakone Onsen Day Pass")
    assert "- **Type**: onsen" in markdown
    assert "- **Pricing mode**: per_uom" in markdown
    assert "Full-day onsen access with mountain view." in markdown
    assert "rfq_engine" in markdown


@pytest.mark.unit
def test_markdown_projection_provider_item_spec_dict():
    markdown = _project_markdown("provider_item", dict(_PROVIDER_ITEM_ROW))
    assert markdown.startswith("# Provider Item: ONS-DAY-7")
    assert "- **supplier_name**: Hakone Kanko" in markdown
    assert "- **cabin_class**: open-air" in markdown


@pytest.mark.unit
def test_markdown_projection_quote():
    markdown = _project_markdown("quote", dict(_QUOTE_ROW))
    assert markdown.startswith("# Quote:")
    assert "- **Request UUID**: u-req-1" in markdown
    assert "- **Total quote amount**: 240.0" in markdown


@pytest.mark.unit
def test_tags_include_entity_metadata():
    tags = catalog_ingest._tags_for("provider_item", dict(_PROVIDER_ITEM_ROW))
    assert "provider_item" in tags and "rfq_engine" in tags
    assert "corp-7" in tags


# --- Single-entity ingestion ------------------------------------------------ #


@pytest.mark.unit
def test_ingest_missing_settings_fails_fast(info, invoker, repos, monkeypatch):
    """R2: no provisioned domain/type -> in-band configuration_error; KE is
    never invoked and RFQ never auto-creates domains/types."""
    monkeypatch.setattr(
        catalog_ingest.Config, "get_setting", lambda: {"functs_on_local": {}}
    )
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_CONFIGURATION_ERROR
    assert result["error_code"] == "configuration_error"
    assert "domain_id" in result["error_message"]
    assert invoker.calls == []


@pytest.mark.unit
def test_ingest_missing_type_for_entity_fails_fast(info, invoker, repos, setting):
    partial = {
        "functs_on_local": _SETTING["functs_on_local"],
        "knowledge_engine_ingest": {
            "domain_id": "domain-rfq",
            "type_ids": {"item": "type-item"},
        },
    }
    catalog_ingest.Config.get_setting = lambda: partial
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="quote", uuid="u-quote-1", parent_uuid="u-req-1"
    )
    assert result["status"] == STATUS_CONFIGURATION_ERROR
    assert "type_ids.quote" in result["error_message"]


@pytest.mark.unit
def test_ingest_unknown_entity_type(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="warp_drive", uuid="u-1"
    )
    assert result["status"] == STATUS_NOT_SUPPORTED
    assert result["error_code"] == "operation_unsupported"
    assert invoker.calls == []


@pytest.mark.unit
def test_ingest_entity_not_found(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-missing"
    )
    assert result["status"] == STATUS_NOT_FOUND
    assert result["error_code"] == "not_found"
    assert invoker.calls == []


@pytest.mark.unit
def test_ingest_create_path(info, invoker, repos, setting):
    """First ingest of an entity creates a KE knowledge entry with
    ``code = {entity_type}-{uuid}`` and derived idempotency key."""
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )

    assert result["status"] == STATUS_OK
    assert result["knowledge_id"] == "ke-1"
    assert result["domain_id"] == "domain-rfq"
    assert result["type_id"] == "type-item"
    assert result["idempotency_key"].startswith("rfq:tenant-test:item:u-item-1:")

    ops = [c["op"] for c in invoker.calls]
    assert ops == ["knowledges", "createKnowledge"]
    create_input = invoker.created[0]
    assert create_input["code"] == "item-u-item-1"
    assert create_input["name"] == "Hakone Onsen Day Pass"
    assert create_input["typeId"] == "type-item"
    assert create_input["domainId"] == "domain-rfq"
    assert create_input["automaticVectorization"] is True
    assert create_input["metadata"]["source"] == "rfq_engine"
    assert create_input["metadata"]["uuid"] == "u-item-1"
    assert "Hakone Onsen Day Pass" in create_input["content"]


@pytest.mark.unit
def test_ingest_client_key_prefixes_derived_key(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1", idempotency_key="client-key"
    )
    assert result["status"] == STATUS_OK
    assert result["idempotency_key"].startswith("client-key:rfq:")


@pytest.mark.unit
def test_ingest_replay_unchanged_content_is_noop(info, invoker, repos, setting):
    """T2.4: replaying an unchanged entity returns the existing knowledge
    without a create or update call."""
    catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    invoker.calls.clear()
    invoker.created.clear()
    invoker.updated.clear()

    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )

    assert result["status"] == STATUS_OK
    assert result["knowledge_id"] == "ke-1"
    assert [c["op"] for c in invoker.calls] == ["knowledges"]
    assert invoker.created == [] and invoker.updated == []


@pytest.mark.unit
def test_ingest_changed_entity_updates_existing(info, invoker, repos, setting):
    """Re-ingesting a changed entity updates the existing knowledge entry
    (upsert-by-code), carrying ``expectedUpdatedAt``."""
    catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    invoker.calls.clear()
    # Mutate the RFQ entity (new updated_at + content).
    repos["item"]._rows["u-item-1"] = dict(
        _ITEM_ROW,
        item_name="Hakone Onsen Premium Pass",
        updated_at="2026-10-05T00:00:00Z",
    )

    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )

    assert result["status"] == STATUS_OK
    assert result["knowledge_id"] == "ke-1"
    ops = [c["op"] for c in invoker.calls]
    assert ops == ["knowledges", "updateKnowledge"]
    update_call = invoker.calls[1]
    assert update_call["params"]["variables"]["id"] == "ke-1"
    assert (
        update_call["params"]["variables"]["input"]["expectedUpdatedAt"]
        == "2026-10-19T00:00:00Z"
    )
    assert (
        update_call["params"]["variables"]["input"]["name"]
        == "Hakone Onsen Premium Pass"
    )


@pytest.mark.unit
def test_ingest_lost_create_race_falls_through_to_update(
    info, invoker, repos, setting
):
    """A concurrent creator winning the code race (ALREADY_EXISTS) makes the
    bridge converge through the update path."""
    # First lookup sees nothing; the concurrent creator lands the node before
    # our create is processed, so createKnowledge raises ALREADY_EXISTS and
    # the retry iteration's fresh lookup finds the winner's node.
    invoker.lookup_script = [None]
    invoker.failures["createKnowledge"] = [
        Exception([{"message": "BIZ_KNOWLEDGE_ALREADY_EXISTS: code exists"}])
    ]
    invoker.knowledge_by_code["item-u-item-1"] = {
        "id": "ke-race",
        "code": "item-u-item-1",
        "name": "Concurrent Write",
        "status": "DRAFT",
        "content": "different content",
        "updatedAt": "2026-10-18T00:00:00Z",
    }

    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )

    assert result["status"] == STATUS_OK
    assert result["knowledge_id"] == "ke-race"
    ops = [c["op"] for c in invoker.calls]
    assert ops == ["knowledges", "createKnowledge", "knowledges", "updateKnowledge"]


@pytest.mark.unit
def test_ingest_version_conflict_retries_once(info, invoker, repos, setting):
    invoker.knowledge_by_code["item-u-item-1"] = {
        "id": "ke-1",
        "code": "item-u-item-1",
        "status": "DRAFT",
        "content": "different content",
        "updatedAt": "2026-10-18T00:00:00Z",
    }
    invoker.failures["updateKnowledge"] = [
        Exception([{"message": "BIZ_KNOWLEDGE_VERSION_CONFLICT: stale expected_at"}])
    ]

    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )

    assert result["status"] == STATUS_OK
    ops = [c["op"] for c in invoker.calls]
    # First update conflicts, the retry's fresh lookup succeeds.
    assert ops == ["knowledges", "updateKnowledge", "knowledges", "updateKnowledge"]


@pytest.mark.unit
def test_ingest_maps_access_denied_in_band(info, invoker, repos, setting):
    invoker.failures["createKnowledge"] = [
        Exception([{"message": "BIZ_KNOWLEDGE_PERMISSION: knowledge:write required"}])
    ]
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_ACCESS_DENIED
    assert result["error_code"] == "access_denied"


@pytest.mark.unit
def test_ingest_maps_timeout_in_band(info, invoker, repos, setting):
    invoker.failures["knowledges"] = [
        Exception([{"message": "BIZ_KNOWLEDGE_TIMEOUT: neo4j timed out"}])
    ]
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_TIMEOUT
    assert result["error_code"] == "system_timeout"


@pytest.mark.unit
def test_ingest_maps_other_errors_in_band(info, invoker, repos, setting):
    invoker.failures["createKnowledge"] = [
        Exception([{"message": "BIZ_KNOWLEDGE_VALIDATION: name empty"}])
    ]
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_ERROR
    assert result["error_code"] == "system_error"


@pytest.mark.unit
def test_ingest_requires_partition_key(info, invoker, repos, setting):
    from rfq_engine.handlers.catalog import CatalogSystemError

    info.context["partition_key"] = None
    with pytest.raises(CatalogSystemError, match="partition_key"):
        catalog_ingest.dispatch_ingest_knowledge(
            info, entity_type="item", uuid="u-item-1"
        )


# --- ItemCatalogRef auto-sync (T2.7) ----------------------------------------- #


@pytest.mark.unit
def test_successful_ingest_syncs_item_catalog_ref(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_OK
    ref_calls = repos["item_catalog_ref"].insert_update_calls
    assert len(ref_calls) == 1
    call = ref_calls[0]
    assert call["namespace"] == "KE"
    assert call["node_id"] == "ke-1"  # node_id = KE knowledge id
    assert call["item_uuid"] == "u-item-1"
    assert call["status"] == "active"


@pytest.mark.unit
def test_sync_can_be_disabled(info, invoker, repos, monkeypatch):
    disabled = dict(_SETTING)
    disabled["knowledge_engine_ingest"] = dict(
        _SETTING["knowledge_engine_ingest"], sync_item_catalog_ref=False
    )
    monkeypatch.setattr(catalog_ingest.Config, "get_setting", lambda: disabled)

    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_OK
    assert repos["item_catalog_ref"].insert_update_calls == []


@pytest.mark.unit
def test_ref_sync_failure_is_not_fatal(info, invoker, repos, setting, monkeypatch):
    def _boom(info, **kwargs):
        raise RuntimeError("ref sync exploded")

    monkeypatch.setattr(
        repos["item_catalog_ref"], "insert_update", lambda info, **kwargs: _boom(info, **kwargs)
    )
    result = catalog_ingest.dispatch_ingest_knowledge(
        info, entity_type="item", uuid="u-item-1"
    )
    assert result["status"] == STATUS_OK


# --- Batch ingestion (T2.5) -------------------------------------------------- #


@pytest.mark.unit
def test_batch_ingests_items_and_provider_items(info, invoker, repos, setting):
    repos["provider_item"].list_rows = [dict(_PROVIDER_ITEM_ROW)]

    batch = catalog_ingest.dispatch_ingest_catalog(
        info, item_uuids=["u-item-1"], include_provider_items=True
    )

    assert batch["requested"] == 2  # item + provider item
    assert batch["ingested"] == 2
    assert batch["failed"] == 0
    statuses = {r["entity_type"]: r["status"] for r in batch["results"]}
    assert statuses == {"item": STATUS_OK, "provider_item": STATUS_OK}
    provider_result = next(
        r for r in batch["results"] if r["entity_type"] == "provider_item"
    )
    assert provider_result["knowledge_id"] == "ke-2"


@pytest.mark.unit
def test_batch_reports_partial_failures_with_attribution(
    info, invoker, repos, setting
):
    """Missing items surface as not_found rows; healthy items still ingest."""
    batch = catalog_ingest.dispatch_ingest_catalog(
        info, item_uuids=["u-item-1", "u-missing"], include_provider_items=False
    )

    assert batch["requested"] == 2
    assert batch["ingested"] == 1
    assert batch["failed"] == 1
    missing = next(r for r in batch["results"] if r["entity_uuid"] == "u-missing")
    assert missing["status"] == STATUS_NOT_FOUND
    assert missing["error_code"] == "not_found"


@pytest.mark.unit
def test_batch_configuration_failure_fails_all_rows_in_band(
    info, invoker, repos, monkeypatch
):
    monkeypatch.setattr(
        catalog_ingest.Config, "get_setting", lambda: {"functs_on_local": {}}
    )
    batch = catalog_ingest.dispatch_ingest_catalog(
        info, item_uuids=["u-item-1", "u-item-2"]
    )
    assert batch["ingested"] == 0
    assert batch["failed"] == 2
    assert all(
        r["status"] == STATUS_CONFIGURATION_ERROR for r in batch["results"]
    )


@pytest.mark.unit
def test_batch_requires_uuid_list(info, invoker, repos, setting):
    from rfq_engine.handlers.catalog import CatalogSystemError

    with pytest.raises(CatalogSystemError, match="item_uuids"):
        catalog_ingest.dispatch_ingest_catalog(info, item_uuids=[])


# --- File ingestion (T2.6 / D2) ---------------------------------------------- #


@pytest.mark.unit
def test_file_ingestion_via_presigned_url(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_file(
        info,
        request_uuid="u-req-1",
        file_name="spec.pdf",
        file_url="https://s3.example.com/presigned",
    )
    assert result["status"] == STATUS_OK
    assert result["source_id"] == "src-1"
    assert result["idempotency_key"].startswith("rfq:tenant-test:file:")
    ops = [c["op"] for c in invoker.calls]
    assert ops == ["importKnowledgeFromUrl"]
    variables = invoker.calls[0]["params"]["variables"]
    assert variables["input"]["url"] == "https://s3.example.com/presigned"
    assert variables["input"]["knowledgeTypeId"] == "type-item"
    assert variables["input"]["domainId"] == "domain-rfq"


@pytest.mark.unit
def test_file_ingestion_via_inline_base64(info, invoker, repos, setting):
    import base64

    content = base64.b64encode(b"PDF bytes here").decode()
    result = catalog_ingest.dispatch_ingest_file(
        info,
        request_uuid="u-req-1",
        file_name="spec.pdf",
        file_content=content,
        file_format="application/pdf",
    )
    assert result["status"] == STATUS_OK
    ops = [c["op"] for c in invoker.calls]
    assert ops == ["importKnowledge"]
    variables = invoker.calls[0]["params"]["variables"]
    assert variables["input"]["fileName"] == "spec.pdf"
    assert variables["input"]["fileContent"] == content
    assert variables["input"]["fileFormat"] == "application/pdf"


@pytest.mark.unit
def test_file_ingestion_rejects_invalid_base64(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_file(
        info,
        request_uuid="u-req-1",
        file_name="spec.pdf",
        file_content="not base64!!",
    )
    assert result["status"] == STATUS_ERROR
    assert "base64" in result["error_message"]


@pytest.mark.unit
def test_file_ingestion_without_transport_is_configuration_error(
    info, invoker, repos, setting, monkeypatch
):
    monkeypatch.setattr(catalog_ingest.Config, "aws_s3", None)
    result = catalog_ingest.dispatch_ingest_file(
        info, request_uuid="u-req-1", file_name="spec.pdf"
    )
    assert result["status"] == STATUS_CONFIGURATION_ERROR
    assert "file_bucket" in result["error_message"]


@pytest.mark.unit
def test_file_ingestion_unknown_file_is_not_found(info, invoker, repos, setting):
    result = catalog_ingest.dispatch_ingest_file(
        info, request_uuid="u-req-1", file_name="missing.pdf", file_url="https://x"
    )
    assert result["status"] == STATUS_NOT_FOUND
    assert invoker.calls == []


@pytest.mark.unit
def test_file_ingestion_requires_arguments(info, invoker, repos, setting):
    from rfq_engine.handlers.catalog import CatalogSystemError

    with pytest.raises(CatalogSystemError, match="required"):
        catalog_ingest.dispatch_ingest_file(info, request_uuid="", file_name="")
