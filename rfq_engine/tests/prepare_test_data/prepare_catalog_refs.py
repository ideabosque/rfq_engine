#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Ingest RFQ catalog items into the knowledge_engine and bridge them back
via ``ItemCatalogRef`` (KE-era replacement for the KGE seed script).

End-to-end flow per item in ``products.json`` (items must already exist in
the RFQ store — run ``prepare_products.py`` first):

    1. ``mutation ingestKnowledgeFromRfq(entityType: "item", uuid: ...)``
       on the RFQ Engine — the ingestion bridge projects the item to
       markdown, derives a deterministic idempotency key, upserts a KE
       knowledge entry (``code = item-{uuid}``), and auto-syncs an
       ``ItemCatalogRef`` row.
    2. The returned KE ``knowledgeId`` is the stable bridge identifier —
       ``node_id`` semantics are KE knowledge ids (migration plan §3.2).
    3. For each provider item, ``insertUpdateItemCatalogRef`` links
       ``namespace + nodeId -> (item_uuid, provider_item_uuid)`` with the
       search-relevant ``extra`` metadata.

Everything runs through ``silvaengine_utility.Invoker``'s
``invoke_funct_on_local`` against ``rfq_graphql`` — the same call shape
as ``handlers/catalog/ingest.py`` (the bridge validates its own settings
and fails in-band with ``configuration_error`` when the tenant is not
provisioned — run ``prepare_ke_provisioning.py`` first).

Usage::

    python rfq_engine/tests/prepare_test_data/prepare_catalog_refs.py

Configurable via env vars (see ``prepare_ke_provisioning.py`` for the
``ke_domain_id`` / ``ke_type_*`` provisioning values)::

    SEED_CATALOG_INPUT=products.json          # filename in SEED_CATALOG_INPUT_DIR
    SEED_CATALOG_INPUT_DIR=dds               # subfolder (e.g. dds, travel)
    SEED_CATALOG_OUTPUT_DIR=dds               # subfolder for output
    SEED_CATALOG_NAMESPACE=KE                 # ItemCatalogRef namespace
    SEED_CATALOG_SKIP_INGEST=0                # 1 = link-only; search KE for an existing node
    SEED_CATALOG_SEARCH_MODE=semantic         # used when SKIP_INGEST=1
    SEED_CATALOG_TOP_K=10                      # used when SKIP_INGEST=1

Writes ``catalog_refs.json`` to ``SEED_CATALOG_OUTPUT_DIR``.
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
logger = logging.getLogger("prepare_catalog_refs")


UPDATED_BY = "prepare_catalog_refs"
HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SUBDIR = os.getenv("SEED_CATALOG_SUBDIR", "dds")
INPUT_DIR = os.path.join(HERE, os.getenv("SEED_CATALOG_INPUT_DIR", DEFAULT_SUBDIR))
OUTPUT_DIR = os.path.join(HERE, os.getenv("SEED_CATALOG_OUTPUT_DIR", DEFAULT_SUBDIR))
INPUT_FILE = os.path.join(INPUT_DIR, os.getenv("SEED_CATALOG_INPUT", "products.json"))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "catalog_refs.json")

NAMESPACE = os.getenv("SEED_CATALOG_NAMESPACE", "KE")
SKIP_INGEST = os.getenv("SEED_CATALOG_SKIP_INGEST", "0") == "1"
SEARCH_MODE = os.getenv("SEED_CATALOG_SEARCH_MODE", "semantic")
TOP_K = int(os.getenv("SEED_CATALOG_TOP_K", "10"))


SETTING = build_setting()
# The ingestion bridge invokes KE in-process; it needs both funct entries
# and the per-tenant provisioning values (T0.2 — run
# prepare_ke_provisioning.py first, which emits these env values).
SETTING.setdefault("functs_on_local", {})["knowledge_engine_graphql"] = {
    "module_name": "knowledge_engine",
    "class_name": "KnowledgeEngine",
}
_ingest_type_ids = {
    entity: os.getenv(f"ke_type_{entity}")
    for entity in (
        "item",
        "provider_item",
        "request",
        "quote",
        "bundle",
        "discount_prompt",
    )
}
if os.getenv("ke_domain_id"):
    SETTING["knowledge_engine_ingest"] = {
        "domain_id": os.getenv("ke_domain_id"),
        "type_ids": {k: v for k, v in _ingest_type_ids.items() if v},
        "namespace": NAMESPACE,
        "sync_item_catalog_ref": os.getenv("ke_sync_refs", "1") == "1",
    }


# --- GraphQL ---------------------------------------------------------------- #

_INGEST_KNOWLEDGE_MUTATION = """
mutation IngestKnowledgeFromRfq($entityType: String!, $uuid: String!) {
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

_INQUIRE_CATALOG_QUERY = """
query InquireCatalog($namespace: String, $query: JSONCamelCase) {
    inquireCatalog(namespace: $namespace, query: $query) {
        namespace nodeId payload errorCode errorMessage
    }
}
"""

ITEM_CATALOG_REF_MUTATION = """
mutation InsertUpdateItemCatalogRef(
    $ns: String, $node: String, $iid: String, $pid: String,
    $extra: JSONCamelCase, $stat: String, $by: String!
) {
    insertUpdateItemCatalogRef(
        namespace: $ns, nodeId: $node, itemUuid: $iid,
        providerItemUuid: $pid, extra: $extra, status: $stat, updatedBy: $by
    ) {
        itemCatalogRef { catalogRefUuid }
    }
}
"""


# --- Invocation ------------------------------------------------------------- #

def invoke(query: str, variables: dict) -> dict | None:
    """Call ``rfq_graphql`` through ``Invoker.invoke_funct_on_local``.

    The helper unwraps the body / error envelope and returns the GraphQL
    ``data`` payload.
    """
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
    except Exception as exc:
        logger.error("Invoke rfq_graphql failed: %s", exc)
        return None


# --- Bridge ingestion -------------------------------------------------------- #

def ingest_into_ke(item: dict) -> dict | None:
    """Push one RFQ item into the knowledge engine via the ingestion bridge.

    The bridge owns markdown projection, deterministic idempotency keys,
    upsert-by-code, and the ItemCatalogRef auto-sync (T2.7).
    """
    item_uuid = item.get("itemUuid")
    if not item_uuid:
        logger.error("  item missing itemUuid; skipping")
        return None
    data = invoke(
        _INGEST_KNOWLEDGE_MUTATION,
        {"entityType": "item", "uuid": item_uuid},
    )
    result = (
        ((data or {}).get("ingestKnowledgeFromRfq") or {}).get("result")
        if isinstance(data, dict)
        else None
    )
    if not isinstance(result, dict):
        logger.warning("  bridge returned no payload for %s", item_uuid)
        return None
    if result.get("status") != "ok":
        logger.warning(
            "  ingest failed for %s: status=%s error=%s %s",
            item_uuid,
            result.get("status"),
            result.get("errorCode"),
            result.get("errorMessage"),
        )
        return None
    logger.info(
        "  KE ingest: knowledgeId=%s code=item-%s",
        result.get("knowledgeId"),
        item_uuid,
    )
    return result


# --- KE search-based lookup (used when SKIP_INGEST=1) ------------------------ #

def extract_node_identity(result: Any, item_uuid: str) -> dict | None:
    """Pick the KE knowledge id for an item from a search result row.

    The KE envelope results carry ``{id, code, name, ...}``; the exact
    match is the row whose ``code`` equals ``item-{item_uuid}``.
    """
    if not isinstance(result, dict):
        return None
    node_id = result.get("id")
    if not node_id:
        return None
    matched_via = (
        "code:exact" if result.get("code") == f"item-{item_uuid}" else "search:top"
    )
    return {"node_id": str(node_id), "key": matched_via, "code": result.get("code")}


def lookup_existing_node(item: dict, query_text: str) -> dict | None:
    item_uuid = item.get("itemUuid")
    data = invoke(
        _INQUIRE_CATALOG_QUERY,
        {
            "namespace": NAMESPACE,
            "query": {
                "queryText": query_text,
                "searchMode": SEARCH_MODE,
                "limit": TOP_K,
            },
        },
    )
    inquire = (data or {}).get("inquireCatalog") or {}
    if inquire.get("errorCode"):
        logger.warning(
            "  inquire_catalog error: %s %s",
            inquire.get("errorCode"),
            inquire.get("errorMessage"),
        )
        return None
    payload = inquire.get("payload") or {}
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return None
    # Prefer the exact-code match, then the top hit.
    for result in results:
        identity = extract_node_identity(result, item_uuid or "")
        if identity and identity["key"] == "code:exact":
            return identity
    for result in results:
        identity = extract_node_identity(result, item_uuid or "")
        if identity:
            return identity
    return None


# --- Catalog ref seeder ------------------------------------------------------- #

def upsert_catalog_ref(
    *,
    item: dict,
    provider_item: dict,
    node_id: str,
    extra: dict,
) -> dict | None:
    data = invoke(
        ITEM_CATALOG_REF_MUTATION,
        {
            "ns": NAMESPACE,
            "node": node_id,
            "iid": item["itemUuid"],
            "pid": provider_item["providerItemUuid"],
            "extra": extra,
            "stat": "active",
            "by": UPDATED_BY,
        },
    )
    if not data:
        return None
    catalog_ref_uuid = data["insertUpdateItemCatalogRef"]["itemCatalogRef"][
        "catalogRefUuid"
    ]
    record = {
        "catalogRefUuid": catalog_ref_uuid,
        "namespace": NAMESPACE,
        "nodeId": node_id,
        "itemUuid": item["itemUuid"],
        "providerItemUuid": provider_item["providerItemUuid"],
        "extra": extra,
    }
    logger.info(
        "  catalog_ref: %s %s nodeId=%s -> %s",
        item.get("itemName"),
        provider_item.get("providerItemExternalId"),
        node_id,
        catalog_ref_uuid,
    )
    return record


# --- Orchestrator ------------------------------------------------------------ #

def load_input() -> dict:
    if not os.path.isfile(INPUT_FILE):
        raise RuntimeError(
            f"Input file not found: {INPUT_FILE}. Run "
            "prepare_products.py first."
        )
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def index_by(items: list[dict], key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in items:
        k = entry.get(key)
        if k:
            grouped.setdefault(k, []).append(entry)
    return grouped


def index_one_by(items: list[dict], key: str) -> dict[str, dict]:
    return {entry[key]: entry for entry in items if entry.get(key)}


def build_search_text(item: dict, provider_items: list[dict]) -> str:
    """Semantic query text for link-only mode (item identity first)."""
    parts = [item.get("itemName"), item.get("itemExternalId")]
    spec = (provider_items[0].get("itemSpec") if provider_items else {}) or {}
    if spec.get("supplier_name") or spec.get("airline_name"):
        parts.append(spec.get("supplier_name") or spec.get("airline_name"))
    return " ".join(p for p in parts if p)


def generate() -> dict:
    if not SETTING.get("endpoint_id") or not SETTING.get("part_id"):
        raise RuntimeError(
            "endpoint_id and part_id must be set in tests/.env before running"
        )
    if not SKIP_INGEST and not SETTING.get("knowledge_engine_ingest"):
        raise RuntimeError(
            "knowledge_engine_ingest settings missing — run "
            "prepare_ke_provisioning.py first and export the ke_domain_id / "
            "ke_type_item values (or set SEED_CATALOG_SKIP_INGEST=1)"
        )

    products_data = load_input()
    items = products_data.get("items") or []
    provider_items_by_item = index_by(
        products_data.get("provider_items") or [], "itemUuid"
    )
    bundle_components_by_item = index_by(
        products_data.get("bundle_components") or [], "itemUuid"
    )
    bundles_by_uuid = index_one_by(products_data.get("bundles") or [], "bundleUuid")

    output: dict[str, Any] = {
        "namespace": NAMESPACE,
        "skipIngest": SKIP_INGEST,
        "ingested": [],
        "matched": [],
        "unmatched": [],
    }

    mode = "link-only (skip ingest)" if SKIP_INGEST else "ingest + link"
    logger.info("--- %s mode: %d items (KE bridge) ---", mode, len(items))

    for idx, item in enumerate(items, start=1):
        item_uuid = item.get("itemUuid")
        external_id = item.get("itemExternalId") or item_uuid
        logger.info(
            "[%d/%d] %s (%s)", idx, len(items), item.get("itemName"), external_id
        )

        siblings = provider_items_by_item.get(item_uuid, [])
        if not siblings:
            logger.warning("  no provider items; skipping")
            continue

        item_components = bundle_components_by_item.get(item_uuid, [])

        node_id: str | None = None
        ingest_result: dict | None = None
        matched_via: str | None = None

        if SKIP_INGEST:
            query_text = build_search_text(item, siblings)
            identity = lookup_existing_node(item, query_text)
            if identity:
                node_id = identity["node_id"]
                matched_via = identity.get("key")
                logger.info(
                    "  KE lookup: nodeId=%s (via %s)", node_id, matched_via
                )
            else:
                logger.error("  no usable KE nodeId for %s; skipping", external_id)
                output["unmatched"].append(
                    {"itemUuid": item_uuid, "queryText": query_text}
                )
                continue
        else:
            ingest_result = ingest_into_ke(item)
            if not ingest_result:
                logger.error(
                    "  ingest failed for %s; skipping catalog ref", external_id
                )
                output["unmatched"].append(
                    {
                        "itemUuid": item_uuid,
                        "itemExternalId": item.get("itemExternalId"),
                        "reason": "ke_ingest_failed",
                    }
                )
                continue
            node_id = ingest_result.get("knowledgeId")
            matched_via = "ingest:knowledgeId"

        if not node_id:
            logger.error("  resolved nodeId is empty for %s; skipping", external_id)
            continue

        output["ingested"].append(
            {
                "itemUuid": item_uuid,
                "itemExternalId": item.get("itemExternalId"),
                "knowledgeId": node_id,
                "matchedVia": matched_via,
            }
        )

        for provider_item in siblings:
            spec = provider_item.get("itemSpec") or {}
            extra = {
                "itemExternalId": item.get("itemExternalId"),
                "providerItemExternalId": provider_item.get(
                    "providerItemExternalId"
                ),
                "supplierCode": spec.get("supplier_code") or spec.get("airline_code"),
                "route": (
                    f"{spec.get('origin') or spec.get('origin_iata')}-{spec.get('destination') or spec.get('destination_iata')}"
                    if (spec.get("origin") or spec.get("origin_iata")) and (spec.get("destination") or spec.get("destination_iata"))
                    else None
                ),
                "variant": spec.get("variant") or spec.get("cabin_class"),
                "bundleComponents": [
                    {
                        "bundleUuid": component.get("bundleUuid"),
                        "bundleCode": (
                            bundles_by_uuid.get(component.get("bundleUuid"), {}).get(
                                "bundleCode"
                            )
                        ),
                        "bundleName": (
                            bundles_by_uuid.get(component.get("bundleUuid"), {}).get(
                                "bundleName"
                            )
                        ),
                        "bundleComponentUuid": component.get(
                            "bundleComponentUuid"
                        ),
                        "componentRole": component.get("componentRole"),
                    }
                    for component in item_components
                ],
                "keResolution": {
                    "matchedVia": matched_via,
                    "knowledgeId": node_id,
                },
            }
            record = upsert_catalog_ref(
                item=item,
                provider_item=provider_item,
                node_id=node_id,
                extra=extra,
            )
            if record:
                output["matched"].append(record)

    return output


def write_output(output: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    logger.info(
        "Wrote: %d ingested, %d matched, %d unmatched -> %s",
        len(output["ingested"]),
        len(output["matched"]),
        len(output["unmatched"]),
        OUTPUT_FILE,
    )


if __name__ == "__main__":
    result = generate()
    write_output(result)
    logger.info("--- Done ---")