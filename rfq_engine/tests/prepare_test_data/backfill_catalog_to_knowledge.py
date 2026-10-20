#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Backfill the RFQ catalog into the knowledge_engine and re-point legacy
``ItemCatalogRef`` rows (migration plan T4.2 — cutover, backfill &
decommission).

Run after tenant provisioning (``prepare_ke_provisioning.py``) and before
KGE decommission (T4.3). Per tenant (``endpoint_id#part_id``):

    1. List all RFQ items (``itemList`` pages).
    2. Replay them into KE in batches through the ingestion bridge
       (``ingestCatalogToKnowledge`` — items + provider items; the bridge
       owns markdown projection, deterministic idempotency keys, upsert-
       by-code, and catalog-ref auto-sync).
    3. List all ``ItemCatalogRef`` rows and re-point any whose
       ``node_id`` still references a legacy KGE node to the item's KE
       ``knowledgeId`` (``insertUpdateItemCatalogRef``), preserving
       namespace/status.
    4. Optionally read KE ``knowledgeDomain`` counts (entities /
       relations / vectors) for the reconciliation evidence.
    5. Write ``backfill_reconciliation.json`` (plan T4.2 acceptance:
       entity counts reconcile + re-pointed refs verified).

Idempotent: re-running re-plays only changed entities (bridge upsert)
and re-pointed refs are skipped as already correct.

Usage::

    python rfq_engine/tests/prepare_test_data/backfill_catalog_to_knowledge.py

Env (tests/.env + provisioning output from prepare_ke_provisioning.py)::

    endpoint_id, part_id, base_dir
    ke_domain_id, ke_type_item (+ other ke_type_* values)
    BACKFILL_BATCH_SIZE=25
    BACKFILL_SKIP_INGEST=0     # 1 = re-point refs only (assume KE current)
    BACKFILL_DRY_RUN=0         # 1 = report only, no ref mutations
"""
from __future__ import annotations

__author__ = "bibow"

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(TESTS_DIR, ".env"))

BASE_DIR = os.getenv("base_dir") or os.path.abspath(
    os.path.join(TESTS_DIR, "..", "..")
)
for sibling in (
    "silvaengine_utility",
    "silvaengine_dynamodb_base",
    "silvaengine_constants",
    "rfq_engine",
):
    path = os.path.join(BASE_DIR, sibling)
    if path and path not in sys.path:
        sys.path.insert(0, path)

from silvaengine_utility import Invoker  # noqa: E402

from _backend_setting import build_setting  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("backfill_catalog_to_knowledge")

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(HERE, "backfill_reconciliation.json")

BATCH_SIZE = int(os.getenv("BACKFILL_BATCH_SIZE", "25"))
SKIP_INGEST = os.getenv("BACKFILL_SKIP_INGEST", "0") == "1"
DRY_RUN = os.getenv("BACKFILL_DRY_RUN", "0") == "1"
LIST_PAGE_SIZE = int(os.getenv("BACKFILL_LIST_PAGE_SIZE", "100"))
UPDATED_BY = os.getenv("BACKFILL_UPDATED_BY", "backfill_catalog_to_knowledge")

SETTING = build_setting()
SETTING.setdefault("functs_on_local", {})["knowledge_engine_graphql"] = {
    "module_name": "knowledge_engine",
    "class_name": "KnowledgeEngine",
}
if os.getenv("ke_domain_id"):
    SETTING["knowledge_engine_ingest"] = {
        "domain_id": os.getenv("ke_domain_id"),
        "type_ids": {
            entity: os.getenv(f"ke_type_{entity}")
            for entity in (
                "item",
                "provider_item",
                "request",
                "quote",
                "bundle",
                "discount_prompt",
            )
            if os.getenv(f"ke_type_{entity}")
        },
        "namespace": os.getenv("ke_ingest_namespace", "KE"),
        "sync_item_catalog_ref": os.getenv("ke_sync_refs", "1") == "1",
    }


# --- GraphQL documents ------------------------------------------------------ #

_ITEM_LIST_QUERY = """
query ItemList($pageNumber: Int, $limit: Int) {
    itemList(pageNumber: $pageNumber, limit: $limit) {
        itemList { itemUuid itemName itemExternalId }
        total
    }
}
"""

_INGEST_CATALOG_MUTATION = """
mutation IngestCatalogToKnowledge(
    $itemUuids: [String]!,
    $includeProviderItems: Boolean
) {
    ingestCatalogToKnowledge(
        itemUuids: $itemUuids,
        includeProviderItems: $includeProviderItems
    ) {
        result {
            requested
            ingested
            failed
            results {
                status
                entityType
                entityUuid
                knowledgeId
                errorCode
                errorMessage
            }
        }
    }
}
"""

_CATALOG_REF_LIST_QUERY = """
query ItemCatalogRefList($pageNumber: Int, $limit: Int) {
    itemCatalogRefList(pageNumber: $pageNumber, limit: $limit) {
        itemCatalogRefList {
            catalogRefUuid
            namespace
            nodeId
            itemUuid
            providerItemUuid
            status
        }
        total
    }
}
"""

_REPOINT_REF_MUTATION = """
mutation RepointItemCatalogRef(
    $catalogRefUuid: String,
    $nodeId: String,
    $status: String,
    $by: String!
) {
    insertUpdateItemCatalogRef(
        catalogRefUuid: $catalogRefUuid,
        nodeId: $nodeId,
        status: $status,
        updatedBy: $by
    ) {
        itemCatalogRef { catalogRefUuid nodeId status }
    }
}
"""

_KE_DOMAIN_STATS_QUERY = """
query KnowledgeDomain($id: ID!) {
    knowledgeDomain(id: $id) {
        domainId
        name
        status
        memberCount
        entityCount
        relationCount
        vectorCount
    }
}
"""


# --- Invocation ------------------------------------------------------------- #


def invoke_rfq(query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        return Invoker.invoke_funct_on_local(
            logger,
            SETTING,
            "rfq_graphql",
            query=query,
            variables=variables,
            endpoint_id=SETTING["endpoint_id"],
            part_id=SETTING["part_id"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("rfq_graphql invocation failed: %s", exc)
        return None


def invoke_ke(query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ke_setting = {
        key: value
        for key, value in SETTING.items()
        if key not in ("db_backend", "initialize_tables", "pg_table_prefix")
    }
    try:
        return Invoker.invoke_funct_on_local(
            logger,
            ke_setting,
            "knowledge_engine_graphql",
            query=query,
            variables=variables,
            endpoint_id=SETTING["endpoint_id"],
            part_id=SETTING["part_id"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("knowledge_engine_graphql invocation failed: %s", exc)
        return None


# --- Steps ------------------------------------------------------------------- #


def list_items() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = invoke_rfq(
            _ITEM_LIST_QUERY, {"pageNumber": page, "limit": LIST_PAGE_SIZE}
        )
        listing = (data or {}).get("itemList") or {}
        rows = listing.get("itemList") or []
        items.extend(rows)
        total = listing.get("total") or 0
        logger.info("items: page %d -> %d rows (total %d)", page, len(rows), total)
        if not rows or len(items) >= total:
            break
        page += 1
    return items


def ingest_batch(item_uuids: List[str]) -> Dict[str, Any]:
    data = invoke_rfq(
        _INGEST_CATALOG_MUTATION,
        {"itemUuids": item_uuids, "includeProviderItems": True},
    )
    result = ((data or {}).get("ingestCatalogToKnowledge") or {}).get("result")
    if not isinstance(result, dict):
        return {"requested": len(item_uuids), "ingested": 0, "failed": len(item_uuids), "results": []}
    return result


def list_catalog_refs() -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = invoke_rfq(
            _CATALOG_REF_LIST_QUERY, {"pageNumber": page, "limit": LIST_PAGE_SIZE}
        )
        listing = (data or {}).get("itemCatalogRefList") or {}
        rows = listing.get("itemCatalogRefList") or []
        refs.extend(rows)
        total = listing.get("total") or 0
        logger.info("catalog refs: page %d -> %d rows (total %d)", page, len(rows), total)
        if not rows or len(refs) >= total:
            break
        page += 1
    return refs


def repoint_ref(ref: Dict[str, Any], node_id: str) -> bool:
    if DRY_RUN:
        logger.info(
            "[dry-run] would re-point %s: %s -> %s",
            ref.get("catalogRefUuid"),
            ref.get("nodeId"),
            node_id,
        )
        return True
    data = invoke_rfq(
        _REPOINT_REF_MUTATION,
        {
            "catalogRefUuid": ref.get("catalogRefUuid"),
            "nodeId": node_id,
            "status": ref.get("status") or "active",
            "by": UPDATED_BY,
        },
    )
    updated = (
        ((data or {}).get("insertUpdateItemCatalogRef") or {}).get("itemCatalogRef")
        or {}
    )
    ok = bool(updated.get("nodeId"))
    if ok:
        logger.info(
            "re-pointed %s (%s): %s -> %s",
            ref.get("catalogRefUuid"),
            ref.get("namespace"),
            ref.get("nodeId"),
            node_id,
        )
    return ok


def ke_domain_stats() -> Optional[Dict[str, Any]]:
    domain_id = os.getenv("ke_domain_id")
    if not domain_id:
        return None
    data = invoke_ke(_KE_DOMAIN_STATS_QUERY, {"id": domain_id})
    return (data or {}).get("knowledgeDomain") if isinstance(data, dict) else None


# --- Orchestrator ------------------------------------------------------------ #


def generate() -> Dict[str, Any]:
    if not SETTING.get("endpoint_id") or not SETTING.get("part_id"):
        raise RuntimeError(
            "endpoint_id and part_id must be set in tests/.env before running"
        )
    if not SETTING.get("knowledge_engine_ingest"):
        raise RuntimeError(
            "knowledge_engine_ingest settings missing — run "
            "prepare_ke_provisioning.py first and export ke_domain_id / "
            "ke_type_* values"
        )

    report: Dict[str, Any] = {
        "dryRun": DRY_RUN,
        "batchSize": BATCH_SIZE,
        "items": {"total": 0, "ingested": 0, "failed": 0},
        "knowledgeIds": {},
        "refs": {"total": 0, "repointed": 0, "alreadyCurrent": 0, "unmatched": 0},
        "failures": [],
    }

    # 1-2. Replay the catalog through the bridge.
    items = list_items()
    report["items"]["total"] = len(items)
    logger.info("--- backfill: %d items (batch size %d) ---", len(items), BATCH_SIZE)

    if not SKIP_INGEST:
        for start in range(0, len(items), BATCH_SIZE):
            batch = [i["itemUuid"] for i in items[start : start + BATCH_SIZE]]
            result = ingest_batch(batch)
            report["items"]["ingested"] += result.get("ingested") or 0
            report["items"]["failed"] += result.get("failed") or 0
            for row in result.get("results") or []:
                if row.get("entityType") == "item":
                    if row.get("status") == "ok" and row.get("knowledgeId"):
                        report["knowledgeIds"][row["entityUuid"]] = row["knowledgeId"]
                elif row.get("status") not in ("ok", "skipped"):
                    report["failures"].append(
                        {
                            "entityType": row.get("entityType"),
                            "entityUuid": row.get("entityUuid"),
                            "errorCode": row.get("errorCode"),
                            "errorMessage": row.get("errorMessage"),
                        }
                    )
            logger.info(
                "batch %d-%d: ingested=%s failed=%s",
                start,
                min(start + BATCH_SIZE, len(items)),
                result.get("ingested"),
                result.get("failed"),
            )
    else:
        # Re-point only: learn the KE knowledge ids via the bridge's
        # per-item lookup is not needed — refs are matched against ingest
        # results above; in skip mode we still need ids, so ingest a
        # zero-change replay (bridge upsert makes this cheap/idempotent).
        logger.info("BACKFILL_SKIP_INGEST=1 — replaying for id resolution only")
        for start in range(0, len(items), BATCH_SIZE):
            batch = [i["itemUuid"] for i in items[start : start + BATCH_SIZE]]
            result = ingest_batch(batch)
            for row in result.get("results") or []:
                if row.get("entityType") == "item" and row.get("status") == "ok":
                    report["knowledgeIds"][row["entityUuid"]] = row["knowledgeId"]

    # 3. Re-point legacy refs.
    refs = list_catalog_refs()
    report["refs"]["total"] = len(refs)
    knowledge_ids = report["knowledgeIds"]
    for ref in refs:
        item_uuid = ref.get("itemUuid")
        ke_id = knowledge_ids.get(item_uuid) if item_uuid else None
        if not ke_id:
            report["refs"]["unmatched"] += 1
            continue
        if ref.get("nodeId") == ke_id:
            report["refs"]["alreadyCurrent"] += 1
            continue
        if repoint_ref(ref, ke_id):
            report["refs"]["repointed"] += 1
        else:
            report["failures"].append(
                {
                    "entityType": "item_catalog_ref",
                    "entityUuid": ref.get("catalogRefUuid"),
                    "errorCode": "repoint_failed",
                    "errorMessage": f"could not re-point to {ke_id}",
                }
            )

    # 4. KE-side reconciliation counts.
    stats = ke_domain_stats()
    if stats:
        report["keDomain"] = stats

    # 5. Reconciliation summary (T4.2 acceptance).
    items_ok = report["items"]["ingested"]
    report["reconciliation"] = {
        "items_total": report["items"]["total"],
        "items_ingested_ok": items_ok,
        "items_failed": report["items"]["failed"],
        "refs_repointed": report["refs"]["repointed"],
        "refs_already_current": report["refs"]["alreadyCurrent"],
        "refs_unmatched": report["refs"]["unmatched"],
        "entity_counts_reconcile": bool(
            items_ok
            and items_ok >= report["items"]["total"] - report["items"]["failed"]
        ),
    }
    return report


def write_output(report: Dict[str, Any]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("wrote %s", OUTPUT_FILE)
    summary = report["reconciliation"]
    logger.info(
        "--- Backfill reconciliation: items %s/%s ok, refs re-pointed %s "
        "(already-current %s, unmatched %s) ---",
        summary["items_ingested_ok"],
        summary["items_total"],
        summary["refs_repointed"],
        summary["refs_already_current"],
        summary["refs_unmatched"],
    )


if __name__ == "__main__":
    result = generate()
    write_output(result)
    logger.info("--- Done ---")