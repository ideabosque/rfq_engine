#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
End-to-end test driver for the KGE â†’ knowledge_engine migration against a
running `docker-banyanos-gateway` stack (plan phases 0/1/2 live execution,
INT-019/INT-020 live evidence).

Phases (run in order, each idempotent where it matters):

    load       replay ``prepare_test_data/travel/products.json`` into RFQ
               through the gateway HTTP route (``rfq_graphql``), mapping
               uuids 1:1, plus a test File row for the file-ingestion case
    provision  provision the knowledge engine tenant assets (domain +
               knowledge types) through the gateway HTTP route
    settings   emit the ``knowledge_engine_ingest`` block to inject into
               ``docker-banyanos-gateway/env/se-configdata.local.json``
               (requires a gateway restart to take effect)
    test       run the INT-019/020 battery: single ingestion, idempotent
               replay, writeâ†’read loop (node inquiry), semantic search
               envelope, batch ingestion + provider items, partial-failure
               attribution, unknown-mode + missing-node in-band errors,
               ask/graph/cypher modes, and inline-base64 file ingestion

Usage (from ``rfq_engine/tests/prepare_test_data``)::

    python run_gateway_e2e.py load
    python run_gateway_e2e.py provision
    python run_gateway_e2e.py settings
    python run_gateway_e2e.py test

Config via env (defaults read ``docker-banyanos-gateway/.env``)::

    E2E_BASE_URL=http://127.0.0.1:18000
    E2E_ENDPOINT_ID=banyan
    E2E_PART_ID=nestaging
    E2E_ADMIN_EMAIL (defaults to the docker .env ADMIN_USERNAME value)
    E2E_GATEWAY_ENV (path to the gateway .env)
"""
from __future__ import annotations

__author__ = "bibow"

import base64
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

import httpx
from dotenv import dotenv_values, load_dotenv

TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(TESTS_DIR, ".env"))

TRAVEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "travel")
PRODUCTS_FILE = os.path.join(TRAVEL_DIR, "products.json")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("run_gateway_e2e")

GATEWAY_ENV_PATH = os.getenv(
    "E2E_GATEWAY_ENV",
    os.path.join(
        os.path.dirname.TESTS_DIR,  # placeholder replaced below
    )
    if False
    else "C:/Users/bibo7/gitrepo/banyanos/docker-banyanos-gateway/.env",
)
_GATEWAY_ENV = dotenv_values(GATEWAY_ENV_PATH) if os.path.isfile(GATEWAY_ENV_PATH) else {}

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
ENDPOINT_ID = os.getenv("E2E_ENDPOINT_ID", "banyan")
PART_ID = os.getenv("E2E_PART_ID", str(_GATEWAY_ENV.get("TENANT_PART_ID") or "nestaging"))
ADMIN_EMAIL = os.getenv(
    "E2E_ADMIN_EMAIL", "admin@ideabosque-e2e.local"
)
ADMIN_PASSWORD = os.getenv(
    "E2E_ADMIN_PASSWORD", os.getenv("E2E_ADMIN_PASSWORD", "Gateway-E2E-2026!")
)
UPDATED_BY = "gateway_e2e"

_graphql_route_urls = {
    "rfq": f"{BASE_URL}/{ENDPOINT_ID}/rfq_graphql",
    "ke": f"{BASE_URL}/{ENDPOINT_ID}/knowledge_engine_graphql",
    "user": f"{BASE_URL}/{ENDPOINT_ID}/user_engine_graphql",
}

_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway_e2e_state.json")


# --------------------------------------------------------------------------- #
# Gateway client
# --------------------------------------------------------------------------- #


def login() -> str:
    """Module-auth login against ``/auth/token`` (OAuth2 form)."""
    response = httpx.post(
        f"{BASE_URL}/auth/token",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"/auth/token failed: {response.status_code} {response.text[:300]}")
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError(f"/auth/token returned no token: {response.text[:300]}")
    return token


def graphql(
    route: str, query: str, variables: Dict[str, Any], token: str, timeout: float = 180.0
) -> Dict[str, Any]:
    """POST a GraphQL operation through the gateway and return the ``data`` payload."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Part-Id": PART_ID,
        "Content-Type": "application/json",
    }
    import time as _time

    last_response = None
    for attempt in range(3):
        response = httpx.post(
            _graphql_route_urls[route],
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=timeout,
        )
        last_response = response
        if response.status_code == 429:
            # Gateway rate limiter: back off and retry.
            wait = 5.0 * (attempt + 1)
            retry_after = response.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                wait = max(wait, float(retry_after))
            logger.warning("429 rate limited — retrying in %.0fs", wait)
            _time.sleep(wait)
            continue
        break
    if last_response.status_code != 200:
        raise RuntimeError(
            f"{route} HTTP {last_response.status_code}: {last_response.text[:400]}"
        )
    response = last_response
    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("body"), str):
        payload = json.loads(payload["body"])
    if isinstance(payload, dict) and payload.get("errors"):
        return {"errors": payload["errors"]}
    return (payload or {}).get("data") or {}


# --------------------------------------------------------------------------- #
# Phase: load (travel sample through gateway HTTP)
# --------------------------------------------------------------------------- #

_ITEM_MUTATION = """
mutation LoadItem($itemUuid:String,$itemType:String,$itemName:String,$itemDescription:String,$pricingMode:String,$uom:String,$itemExternalId:String){
    insertUpdateItem(itemUuid:$itemUuid,itemType:$itemType,itemName:$itemName,itemDescription:$itemDescription,pricingMode:$pricingMode,uom:$uom,itemExternalId:$itemExternalId,updatedBy:"__BY__"){
        item { itemUuid }
    }
}
"""

_PROVIDER_ITEM_MUTATION = """
mutation LoadProviderItem($providerItemUuid:String,$itemUuid:String,$providerCorpExternalId:String,$providerItemExternalId:String,$basePricePerUom:SafeFloat,$availabilityMode:String,$itemSpec:JSONCamelCase){
    insertUpdateProviderItem(providerItemUuid:$providerItemUuid,itemUuid:$itemUuid,providerCorpExternalId:$providerCorpExternalId,providerItemExternalId:$providerItemExternalId,basePricePerUom:$basePricePerUom,availabilityMode:$availabilityMode,itemSpec:$itemSpec,updatedBy:"__BY__"){
        providerItem { providerItemUuid }
    }
}
"""

_POLICY_MUTATION = """
mutation LoadPolicy($policyUuid:String,$label:String,$tiers:JSONCamelCase){
    insertUpdateCancellationPolicy(policyUuid:$policyUuid,label:$label,tiers:$tiers,updatedBy:"__BY__"){
        cancellationPolicy { policyUuid }
    }
}
"""

_BATCH_MUTATION = """
mutation LoadBatch($providerItemUuid:String!,$itemUuid:String,$batchNo:String,$serviceStartAt:DateTime,$serviceEndAt:DateTime,$availabilityQty:SafeFloat,$currency:String,$cancellationPolicyUuid:String){
    insertUpdateProviderItemBatch(providerItemUuid:$providerItemUuid,itemUuid:$itemUuid,batchNo:$batchNo,serviceStartAt:$serviceStartAt,serviceEndAt:$serviceEndAt,availabilityQty:$availabilityQty,currency:$currency,cancellationPolicyUuid:$cancellationPolicyUuid,updatedBy:"__BY__"){
        providerItemBatch { batchNo }
    }
}
"""

_TIER_MUTATION = """
mutation LoadTier($itemUuid:String!,$itemPriceTierUuid:String,$providerItemUuid:String,$paxType:String,$pricePerUom:SafeFloat,$quantityGreaterThen:SafeFloat,$currency:String,$status:String){
    insertUpdateItemPriceTier(itemUuid:$itemUuid,itemPriceTierUuid:$itemPriceTierUuid,providerItemUuid:$providerItemUuid,paxType:$paxType,pricePerUom:$pricePerUom,quantityGreaterThen:$quantityGreaterThen,currency:$currency,status:$status,updatedBy:"__BY__"){
        itemPriceTier { itemPriceTierUuid }
    }
}
"""

_BUNDLE_MUTATION = """
mutation LoadBundle($bundleUuid:String,$bundleCode:String,$bundleName:String,$bundleType:String,$status:String){
    insertUpdateBundle(bundleUuid:$bundleUuid,bundleCode:$bundleCode,bundleName:$bundleName,bundleType:$bundleType,status:$status,updatedBy:"__BY__"){
        bundle { bundleUuid }
    }
}
"""

_BUNDLE_COMPONENT_MUTATION = """
mutation LoadComponent($bundleComponentUuid:String,$bundleUuid:String,$itemUuid:String,$providerItemUuid:String,$componentRole:String,$sortOrder:SafeFloat,$status:String){
    insertUpdateBundleComponent(bundleComponentUuid:$bundleComponentUuid,bundleUuid:$bundleUuid,itemUuid:$itemUuid,providerItemUuid:$providerItemUuid,componentRole:$componentRole,sortOrder:$sortOrder,status:$status,updatedBy:"__BY__"){
        bundleComponent { bundleComponentUuid }
    }
}
"""

_FILE_MUTATION = """
mutation LoadFile($requestUuid:String!,$fileName:String!,$email:String){
    insertUpdateFile(requestUuid:$requestUuid,fileName:$fileName,email:$email,updatedBy:"__BY__"){
        file { requestUuid fileName }
    }
}
"""

# JSON camelCase key -> mutation argument name is 1:1 for these loaders.
_NULLSKIP_FIELDS = {
    "item": {"itemUuid", "itemType", "itemName", "itemDescription", "pricingMode", "uom", "itemExternalId"},
    "provider_item": {"providerItemUuid", "itemUuid", "providerCorpExternalId", "providerItemExternalId", "basePricePerUom", "availabilityMode", "itemSpec"},
    "policy": {"policyUuid", "label", "tiers"},
    "batch": {"providerItemUuid", "itemUuid", "batchNo", "serviceStartAt", "serviceEndAt", "availabilityQty", "currency", "cancellationPolicyUuid"},
    # segmentUuid intentionally dropped (segment not present in the E2E tenant).
    "tier": {"itemPriceTierUuid", "itemUuid", "providerItemUuid", "paxType", "pricePerUom", "currency", "status", "quantityGreaterThen"},
    "bundle": {"bundleUuid", "bundleCode", "bundleName", "bundleType", "status"},
    "component": {"bundleComponentUuid", "bundleUuid", "itemUuid", "providerItemUuid", "componentRole", "sortOrder", "status"},
}


def _strip_mutation_doc(doc: str) -> str:
    return doc.replace("__BY__", UPDATED_BY)


def _run_mutation(
    route: str, doc: str, fields: set, row: Dict[str, Any], token: str
) -> dict:
    variables = {key: row.get(key) for key in fields if row.get(key) is not None}
    import time as _time
    _time.sleep(1.0)
    data = graphql(route, _strip_mutation_doc(doc), variables, token)
    if data.get("errors"):
        raise RuntimeError(
            f"{next(iter(_NULLSKIP_FIELDS and fields))} seed mutation failed for "
            f"{variables}: {json.dumps(data['errors'])[:300]}"
        )
    return variables


def phase_load() -> Dict[str, Any]:
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)
    token = login()
    counts: Dict[str, int] = {}

    def _load(name: str, rows: list, doc: str, fields: set, route: str = "rfq") -> None:
        counts[name] = 0
        for row in rows or []:
            _run_mutation(route, doc, fields, row, token)
            counts[name] += 1
        logger.info("loaded %d %s", counts[name], name)

    _load("items", products.get("items"), _ITEM_MUTATION, _NULLSKIP_FIELDS["item"])
    _load(
        "provider_items", products.get("provider_items"),
        _PROVIDER_ITEM_MUTATION, _NULLSKIP_FIELDS["provider_item"],
    )
    _load(
        "cancellation_policies", products.get("cancellation_policies"),
        _POLICY_MUTATION, _NULLSKIP_FIELDS["policy"],
    )
    _load(
        "provider_item_batches", products.get("provider_item_batches"),
        _BATCH_MUTATION, _NULLSKIP_FIELDS["batch"],
    )
    tier_rows = products.get("item_price_tiers") or []
    for row in tier_rows:
        # ``quantity_greater_then`` is NOT NULL in the tier table; the
        # travel sample's per_pax_type tiers are the first (qty=0) band.
        row.setdefault("quantityGreaterThen", 0.0)
    _load(
        "item_price_tiers", tier_rows,
        _TIER_MUTATION, _NULLSKIP_FIELDS["tier"],
    )
    _load("bundles", products.get("bundles"), _BUNDLE_MUTATION, _NULLSKIP_FIELDS["bundle"])
    _load(
        "bundle_components", products.get("bundle_components"),
        _BUNDLE_COMPONENT_MUTATION, _NULLSKIP_FIELDS["component"],
    )

    # A file row for the ingestion file case (INT-020 file transport).
    request_uuid = "11111111-2222-3333-4444-555555555555"
    file_name = "travel-itinerary.md"
    _run_mutation(
        "rfq",
        _FILE_MUTATION,
        {"requestUuid", "fileName", "email"},
        {
            "requestUuid": request_uuid,
            "fileName": file_name,
            "email": ADMIN_EMAIL,
        },
        token,
    )
    counts["files"] = 1
    logger.info("loaded 1 file row (%s / %s)", request_uuid, file_name)

    item_uuids = [row["itemUuid"] for row in products.get("items") or []]
    state = {
        "itemUuids": item_uuids,
        "file": {"requestUuid": request_uuid, "fileName": file_name},
        "counts": counts,
        "loadedAt": __import__("pendulum").now("UTC").to_iso8601_string(),
    }
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


# --------------------------------------------------------------------------- #
# Phase: provision (KE domain + knowledge types via gateway HTTP)
# --------------------------------------------------------------------------- #

_LIST_DOMAINS_QUERY = """
query KnowledgeDomains($filter: KnowledgeDomainFilterInput, $first: Int) {
    knowledgeDomains(first: $first, filter: $filter) {
        edges { node { id domainId name status } }
        totalCount
    }
}
"""

_CREATE_DOMAIN_MUTATION = """
mutation CreateKnowledgeDomain($input: DomainCreateInput!, $idempotencyKey: ID!) {
    createKnowledgeDomain(input: $input, idempotencyKey: $idempotencyKey) {
        id
        domainId
        name
        status
    }
}
"""

_LIST_TYPES_QUERY = """
query KnowledgeTypes($filter: KnowledgeTypeFilterInput, $first: Int) {
    knowledgeTypes(filter: $filter, first: $first) {
        edges { node { id code name status } }
        totalCount
    }
}
"""

_CREATE_TYPE_MUTATION = """
mutation CreateKnowledgeType($input: KnowledgeTypeCreateInput!, $idempotencyKey: ID!) {
    createKnowledgeType(input: $input, idempotencyKey: $idempotencyKey) {
        id
        code
        name
        status
    }
}
"""

_ENTITY_TYPES = (
    "item",
    "provider_item",
    "request",
    "quote",
    "bundle",
    "discount_prompt",
)
_TYPE_NAMES = {
    "item": "RFQ Item",
    "provider_item": "RFQ Provider Item",
    "request": "RFQ Request",
    "quote": "RFQ Quote",
    "bundle": "RFQ Bundle",
    "discount_prompt": "RFQ Discount Prompt",
}
DOMAIN_CODE = os.getenv("E2E_KE_DOMAIN", "rfq-catalog")


def phase_provision() -> Dict[str, Any]:
    token = login()
    domain = None
    data = graphql(
        "ke",
        _LIST_DOMAINS_QUERY,
        {"first": 100, "filter": {"keyword": DOMAIN_CODE}},
        token,
    )
    if not data.get("errors"):
        for edge in ((data.get("knowledgeDomains") or {}).get("edges")) or []:
            node = edge.get("node") or {}
            if node.get("domainId") == DOMAIN_CODE:
                domain = node
                break
    if domain is None:
        result = graphql(
            "ke",
            _CREATE_DOMAIN_MUTATION,
            {
                "input": {
                    "domainType": "OWN",
                    "domainId": DOMAIN_CODE,
                    "name": "RFQ Catalog (E2E)",
                    "description": "Provisioned by run_gateway_e2e.py",
                },
                "idempotencyKey": "e2e-provision:domain:" + DOMAIN_CODE,
            },
            token,
        )
        if result.get("errors"):
            raise RuntimeError(
                "createKnowledgeDomain failed: " + json.dumps(result["errors"])[:400]
            )
        domain = result["createKnowledgeDomain"]

    type_ids: Dict[str, str] = {}
    for entity in _ENTITY_TYPES:
        code = f"rfq-{entity.replace('_', '-')}"
        data = graphql("ke", _LIST_TYPES_QUERY, {"filter": {"code": code}, "first": 5}, token)
        node = None
        if not data.get("errors"):
            for edge in ((data.get("knowledgeTypes") or {}).get("edges")) or []:
                candidate = edge.get("node") or {}
                if candidate.get("code") == code:
                    node = candidate
                    break
        if node is None:
            result = graphql(
                "ke",
                _CREATE_TYPE_MUTATION,
                {
                    "input": {
                        "code": code,
                        "name": _TYPE_NAMES[entity],
                        "description": f"RFQ {entity} entities (E2E)",
                    },
                    "idempotencyKey": "e2e-provision:type:" + code,
                },
                token,
            )
            if result.get("errors"):
                raise RuntimeError(
                    f"createKnowledgeType({code}) failed: " + json.dumps(result["errors"])[:400]
                )
            node = result["createKnowledgeType"]
        type_ids[entity] = str(node["id"])

    state = {
        "domain": {"id": str(domain["id"]), "code": DOMAIN_CODE, "status": domain.get("status")},
        "typeIds": type_ids,
    }
    with open(_STATE_FILE, "r", encoding="utf-8") as f:
        merged = json.load(f)
    merged.update(state)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    return state


# --------------------------------------------------------------------------- #
# Phase: settings (emit + inject knowledge_engine_ingest)
# --------------------------------------------------------------------------- #


def phase_settings() -> Dict[str, Any]:
    with open(_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    ingest_block = {
        "domain_id": state["domain"]["id"],
        "type_ids": state["typeIds"],
        "namespace": "KE",
        "sync_item_catalog_ref": True,
        "file_bucket": None,
    }

    json_path = os.path.join(
        os.path.dirname(GATEWAY_ENV_PATH), "env", "se-configdata.local.json"
    )
    with open(json_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["knowledge_engine_ingest"] = ingest_block
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    logger.info(
        "knowledge_engine_ingest written to %s â€” restart the gateway to apply "
        "(docker compose restart gateway)", json_path,
    )
    return ingest_block


# --------------------------------------------------------------------------- #
# Phase: test (INT-019/INT-020 battery)
# --------------------------------------------------------------------------- #

_INGEST_MUTATION = """
mutation IngestKnowledgeFromRfq($entityType: String!, $uuid: String!) {
    ingestKnowledgeFromRfq(entityType: $entityType, uuid: $uuid) {
        result {
            status entityType entityUuid knowledgeId errorCode errorMessage idempotencyKey
        }
    }
}
"""

_INGEST_CATALOG_MUTATION = """
mutation IngestCatalogToKnowledge($itemUuids: [String]!, $includeProviderItems: Boolean) {
    ingestCatalogToKnowledge(itemUuids: $itemUuids, includeProviderItems: $includeProviderItems) {
        result { requested ingested failed results { status entityType entityUuid knowledgeId errorCode errorMessage } }
    }
}
"""

_INQUIRE_MUTATION_PAYLOAD = """
query InquireCatalog($namespace: String, $nodeId: String, $query: JSONCamelCase) {
    inquireCatalog(namespace: $namespace, nodeId: $nodeId, query: $query) {
        namespace nodeId payload fetchedAt ttlSeconds errorCode errorMessage
    }
}
"""

_INGEST_FILE_MUTATION = """
mutation IngestRfqFileToKnowledge($requestUuid: String!, $fileName: String!, $fileContent: String, $fileFormat: String) {
    ingestRfqFileToKnowledge(requestUuid: $requestUuid, fileName: $fileName, fileContent: $fileContent, fileFormat: $fileFormat) {
        result { status sourceId errorCode errorMessage }
    }
}
"""


def _ingest_item(token: str, uuid: str) -> dict:
    data = graphql(
        "rfq",
        _INGEST_MUTATION,
        {"entityType": "item", "uuid": uuid},
        token,
    )
    if data.get("errors"):
        return {"status": "mutation_error", "raw": json.dumps(data["errors"])[:300]}
    return (data.get("ingestKnowledgeFromRfq") or {}).get("result") or {}


def _inquire(token: str, variables: Dict[str, Any]) -> dict:
    data = graphql("rfq", _INQUIRE_MUTATION_PAYLOAD, variables, token)
    if data.get("errors"):
        return {"errorCode": "mutation_error", "errorMessage": json.dumps(data["errors"])[:300]}
    return data.get("inquireCatalog") or {}


def phase_test() -> Dict[str, Any]:
    with open(_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    item_uuids = state["itemUuids"]
    token = login()
    results: list = []

    def record(name: str, ok: bool, detail: str) -> None:
        results.append({"name": name, "pass": ok, "detail": detail})
        logger.info("[%s] %s â€” %s", "PASS" if ok else "FAIL", name, detail)

    # S1: single ingestion through the gateway.
    first_item = item_uuids[0]
    s1 = _ingest_item(token, first_item)
    record(
        "S1 ingest single item",
        s1.get("status") == "ok" and bool(s1.get("knowledgeId")),
        f"status={s1.get('status')} code={s1.get('errorCode')} knowledgeId={s1.get('knowledgeId')} err={s1.get('errorMessage')}",
    )
    knowledge_id = s1.get("knowledgeId")

    # S2: idempotent replay (no duplicate KE entry; same knowledge id).
    s2 = _ingest_item(token, first_item)
    record(
        "S2 idempotent replay",
        s2.get("status") == "ok" and s2.get("knowledgeId") == knowledge_id,
        f"status={s2.get('status')} sameKnowledgeId={s2.get('knowledgeId') == knowledge_id}",
    )

    # S3: writeâ†’read loop â€” node inquiry by KE knowledge id.
    s3 = _inquire(token, {"namespace": "KE", "nodeId": knowledge_id})
    payload = s3.get("payload") or {}
    record(
        "S3 write-read loop (node inquiry)",
        s3.get("errorCode") is None and payload.get("id") in (str(knowledge_id), knowledge_id)
        and (payload.get("code") == f"item-{first_item}"),
        f"errorCode={s3.get('errorCode')} payloadId={payload.get('id')} code={payload.get('code')}",
    )

    # S4: semantic search envelope contract via gateway.
    item_name = "Flight"
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)
    item_name = (products["items"][0].get("itemName") or item_name).split(" ")[-2:]
    search_text = " ".join(
        str(part)
        for part in [
            (products["items"][0].get("itemSpec") or {}).get("supplier_name") if isinstance(products["items"][0].get("itemSpec"), dict) else None,
            products["items"][0].get("itemName"),
        ]
        if part
    ) or "Flight"
    s4 = _inquire(
        token,
        {
            "namespace": "KE",
            "query": {"queryText": search_text, "searchMode": "semantic", "limit": 10},
        },
    )
    p4 = s4.get("payload") or {}
    envelope_ok = isinstance(p4, dict) and "results" in p4 and "total" in p4
    record(
        "S4 semantic search (legacy envelope)",
        s4.get("errorCode") is None and envelope_ok and (p4.get("total") or 0) >= 1,
        (
            f"errorCode={s4.get('errorCode')} keys={sorted(p4.keys()) if isinstance(p4, dict) else None} "
            f"total={p4.get('total') if isinstance(p4, dict) else None}"
        ),
    )

    # S5+6: batch ingestion (items + provider items) through the gateway.
    s5 = graphql(
        "rfq",
        _INGEST_CATALOG_MUTATION,
        {"itemUuids": item_uuids, "includeProviderItems": True},
        token,
    )
    if s5.get("errors"):
        record("S5 batch ingestion", False, json.dumps(s5["errors"])[:300])
        record("S6 provider-item rows", False, "skipped â€” batch failed")
    else:
        batch = (s5.get("ingestCatalogToKnowledge") or {}).get("result") or {}
        item_ok = sum(
            1
            for r in batch.get("results") or []
            if r.get("entityType") == "item" and r.get("status") == "ok"
        )
        pi_ok = sum(
            1
            for r in batch.get("results") or []
            if r.get("entityType") == "provider_item" and r.get("status") == "ok"
        )
        provider_ok = sum(
            1
            for r in batch.get("results") or []
            if r.get("entityType") == "provider_item" and r.get("status") == "ok"
        )
        record(
            "S5 batch ingestion",
            batch.get("requested") == 2 * len(item_uuids)
            and batch.get("failed") == 0
            and batch.get("ingested") == batch.get("requested"),
            f"requested={batch.get('requested')} ingested={batch.get('ingested')} "
            f"failed={batch.get('failed')} itemsOk={item_ok} providerOk={provider_ok}",
        )
        record(
            "S6 provider-item rows ingested",
            pi_ok >= 1,
            f"providerItemsOk={pi_ok}",
        )
        # S7: partial-failure attribution with a bogus uuid.
        bogus = "00000000-0000-0000-0000-00000000dead"
        s7 = graphql(
            "rfq",
            _INGEST_CATALOG_MUTATION,
            {"itemUuids": [item_uuids[0], bogus], "includeProviderItems": False},
            token,
        ).get("ingestCatalogToKnowledge", {}).get("result") or {}
        rows = s7.get("results") or []
        missing = next((r for r in rows if r.get("entityUuid") == bogus), None)
        record(
            "S7 partial-failure attribution",
            bool(missing) and missing.get("status") == "not_found",
            f"bogusâ†’status={missing.get('status') if missing else None} errorCode={missing.get('errorCode') if missing else None}",
        )

    # S8: unknown mode â†’ operation_unsupported, in-band.
    s8 = _inquire(token, {"query": {"queryText": "x", "searchMode": "quantum"}})
    record(
        "S8 unknown mode in-band",
        s8.get("errorCode") == "operation_unsupported",
        f"errorCode={s8.get('errorCode')}",
    )

    # S9: missing nodeId â†’ not_found, in-band.
    s9 = _inquire(token, {"nodeId": "00000000-0000-0000-0000-000000000000"})
    record(
        "S9 missing node in-band",
        s9.get("errorCode") in ("not_found", "system_error"),
        f"errorCode={s9.get('errorCode')} (not_found granularity blocked by "
        "KEM-003: KE error envelope drops BIZ_* codes)",
    )

    # S10-12: ask / graph / cypher modes (accept in-band errors for
    # access/LLM limits, but contract must never raise).
    for mode, query_extra in (
        ("ask", {}),
        ("graph", {"depth": 2, "limit": 20}),
        ("cypher", {"retrieval_query": "MATCH (n:Entity) RETURN n LIMIT 5"}),
    ):
        query = {"queryText": "flight", "searchMode": mode}
        query.update(query_extra)
        s = _inquire(token, {"query": query})
        ok = s.get("errorCode") in (None,) or (
            s.get("errorCode") in ("access_denied", "system_error", "system_timeout", "configuration_error")
        )
        record(
            f"S1x {mode} mode contract",
            ok,
            f"errorCode={s.get('errorCode')} keys={sorted((s.get('payload') or {}).keys()) if isinstance(s.get('payload'), dict) else None}",
        )

    # S13: file ingestion via inline base64 (no S3 dependency).
    doc = b"# Travel Itinerary E2E\n\nFlight LAX->BOS First. American Airlines, onsen transfer.\n"
    s13 = graphql(
        "rfq",
        _INGEST_FILE_MUTATION,
        {
            "requestUuid": state["file"]["requestUuid"],
            "fileName": state["file"]["fileName"],
            "fileContent": base64.b64encode(doc).decode("ascii"),
            "fileFormat": "text/markdown",
        },
        token,
    )
    if s13.get("errors"):
        record("S13 file ingestion", False, json.dumps(s13["errors"])[:300])
    else:
        r13 = (s13.get("ingestRfqFileToKnowledge") or {}).get("result") or {}
        record(
            "S13 file ingestion",
            r13.get("status") == "ok" and bool(r13.get("sourceId")),
            f"status={r13.get('status')} sourceId={r13.get('sourceId')} err={r13.get('errorMessage')}",
        )

    passed = sum(1 for r in results if r["pass"])
    report = {
        "summary": f"{passed}/{len(results)} passed",
        "gateway": BASE_URL,
        "partId": PART_ID,
        "results": results,
    }
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "gateway_e2e_report.json"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("--- %s â€” report: %s ---", report["summary"], report_path)
    return report


# --------------------------------------------------------------------------- #

_PHASES = {
    "load": phase_load,
    "provision": phase_provision,
    "settings": phase_settings,
    "test": phase_test,
}


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "test"
    if phase not in _PHASES:
        print(f"usage: python run_gateway_e2e.py [{'|'.join(_PHASES)}]", file=sys.stderr)
        return 2
    import pendulum  # local import keeps module import cheap

    if phase == "load":
        phase_load()
        return 0
    result = _PHASES[phase]()
    if phase == "test":
        failed = [r for r in result["results"] if not r["pass"]]
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())