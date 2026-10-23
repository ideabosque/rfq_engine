"""Replay existing normalized travel fixtures via gateway GraphQL, then read back IDs.

Uses the live schema for argument types; never regenerates source fixtures or
loads database tables directly. Credentials follow run_gateway_e2e's runtime env.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx
import run_gateway_e2e as gateway

HERE = Path(__file__).resolve().parent
OUTPUT = Path(os.environ.get("AIT_OUTPUT_DIR", HERE.parents[2] / "docs/test_results/travel_gateway_20261020"))
ENTITIES = [
    ("segments", "Segment", "segment", ["segmentUuid"]),
    ("items", "Item", "item", ["itemUuid"]),
    ("provider_items", "ProviderItem", "providerItem", ["providerItemUuid"]),
    ("cancellation_policies", "CancellationPolicy", "cancellationPolicy", ["policyUuid"]),
    ("provider_item_batches", "ProviderItemBatch", "providerItemBatch", ["providerItemUuid", "batchNo"]),
    ("item_price_tiers", "ItemPriceTier", "itemPriceTier", ["itemUuid", "itemPriceTierUuid"]),
    ("bundles", "Bundle", "bundle", ["bundleUuid"]),
    ("bundle_components", "BundleComponent", "bundleComponent", ["bundleUuid", "bundleComponentUuid"]),
    ("discount_prompts", "DiscountPrompt", "discountPrompt", ["discountPromptUuid"]),
]
INTROSPECT = """query { __schema {
  mutationType { fields { name args { name type { kind name ofType { kind name ofType { kind name } } } } } }
  queryType { fields { name args { name type { kind name ofType { kind name ofType { kind name } } } } } }
} }"""


def type_name(t):
    if t["kind"] == "NON_NULL":
        return type_name(t["ofType"]) + "!"
    if t["kind"] == "LIST":
        return "[" + type_name(t["ofType"]) + "]"
    return t["name"]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for attempt in range(20):
        try:
            if httpx.get(gateway.BASE_URL + "/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Gateway did not become healthy within startup grace")
    token = gateway.login()
    calls, results = [], []

    def call(doc, variables, label):
        started = time.monotonic()
        try:
            data = gateway.graphql("rfq", doc, variables, token)
        except Exception as exc:
            data = {"errors": [{"message": str(exc)}]}
        calls.append({"method": "POST " + gateway._graphql_route_urls["rfq"],
                      "description": label, "status": "fail" if data.get("errors") else "pass",
                      "elapsed_ms": round((time.monotonic() - started) * 1000),
                      "arguments": {"query": doc, "variables": variables}, "output": data})
        # Checkpoint evidence even when interrupted.
        (OUTPUT / "travel_fixture_calls.json").write_text(json.dumps(calls, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.65)
        if data.get("errors"):
            raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False)[:600])
        return data

    schema = call(INTROSPECT, {}, "live schema")["__schema"]
    mutations = {f["name"]: {a["name"]: a["type"] for a in f["args"]} for f in schema["mutationType"]["fields"]}
    queries = {f["name"]: {a["name"]: a["type"] for a in f["args"]} for f in schema["queryType"]["fields"]}
    datasets = [json.loads((HERE / "travel" / name).read_text(encoding="utf-8")) for name in ("products.json", "flight_products.json")]
    segments = json.loads((HERE / "segments_and_contacts.json").read_text(encoding="utf-8"))
    prompts = json.loads((HERE / "travel/discount_prompts.json").read_text(encoding="utf-8"))
    datasets.append({"segments": segments["segments"], "discount_prompts": [r for rows in prompts.values() if isinstance(rows, list) for r in rows]})

    def document(operation, name, fields, args, selection):
        definitions = ",".join("$" + k + ":" + type_name(args[k]) for k in fields)
        arguments = ",".join(k + ":$" + k for k in fields)
        return f"{operation}({definitions}){{{name}({arguments}){{{selection}}}}}"

    def batch(operation, name, variable_rows, args, selection, label):
        definitions, fields, variables = [], [], {}
        for i, values in enumerate(variable_rows):
            for k, value in values.items():
                variable = f"r{i}_{k}"
                definitions.append("$" + variable + ":" + type_name(args[k]))
                variables[variable] = value
            passed = ",".join(k + f":$r{i}_" + k for k in values)
            fields.append(f"r{i}:{name}({passed}){{{selection}}}")
        return call(operation + "(" + ",".join(definitions) + "){" + " ".join(fields) + "}", variables, label)

    knowledge_results = []
    completed = False
    try:
        for group, suffix, root, keys in ENTITIES:
            rows = {tuple(str(row.get(k)) for k in keys): dict(row) for d in datasets for row in d.get(group, [])}
            mutation = "insertUpdate" + suffix
            accepted = mutations[mutation]
            unsupported = set()
            source_rows = list(rows.values())
            payloads = []
            for row in source_rows:
                if group == "item_price_tiers":
                    row.setdefault("quantityGreaterThen", 0.0)
                unsupported.update(set(row) - set(accepted))
                variables = {k: v for k, v in row.items() if k in accepted and v is not None}
                variables["updatedBy"] = "travel_fixture_replay"
                payloads.append(variables)
            for offset in range(0, len(payloads), 8):
                data = batch("mutation", mutation, payloads[offset:offset + 8], accepted,
                             root + " { " + " ".join(keys) + " }", "upsert " + group)
                for i, row in enumerate(source_rows[offset:offset + 8]):
                    node = (data.get(f"r{i}") or {}).get(root)
                    if not node or any(str(node.get(k)) != str(row.get(k)) for k in keys):
                        raise RuntimeError(f"{group} identity mismatch: {node}")
            results.append({"entity": group, "loaded": len(rows), "unsupported_source_fields": sorted(unsupported)})
            print(f"LOADED {group}: {len(rows)}; unsupported source fields: {sorted(unsupported)}", flush=True)
            verified = 0
            for offset in range(0, len(source_rows), 20):
                chunk = source_rows[offset:offset + 20]
                query_rows = [{k: row[k] for k in keys if k in queries[root]} for row in chunk]
                data = batch("query", root, query_rows, queries[root], " ".join(keys), "read-back " + group)
                for i, row in enumerate(chunk):
                    node = data.get(f"r{i}")
                    if not node or any(str(node.get(k)) != str(row.get(k)) for k in keys):
                        raise RuntimeError(f"{group} read-back mismatch: {node}")
                    verified += 1
            results[-1]["verified"] = verified
            print(f"VERIFIED {group}: {verified}", flush=True)
        item_ids = list(dict.fromkeys(r["itemUuid"] for d in datasets for r in d.get("items", [])))
        for offset in range(0, len(item_ids), 4):
            batch_ids = item_ids[offset:offset + 4]
            data = call(gateway._INGEST_CATALOG_MUTATION,
                        {"itemUuids": batch_ids, "includeProviderItems": True},
                        "catalog knowledge ingestion")
            outcome = (data.get("ingestCatalogToKnowledge") or {}).get("result") or {}
            knowledge_results.extend(outcome.get("results") or [])
            if outcome.get("failed") != 0 or not outcome.get("ingested"):
                raise RuntimeError("Catalog ingestion failed: " + json.dumps(outcome, ensure_ascii=False)[:1000])
            print(f"KNOWLEDGE batch {offset // 4 + 1}: {outcome.get('ingested')} ingested", flush=True)
        expected = {("item", r["itemUuid"]) for d in datasets for r in d.get("items", [])}
        expected.update(("provider_item", r["providerItemUuid"]) for d in datasets for r in d.get("provider_items", []))
        observed = {(r.get("entityType"), r.get("entityUuid")) for r in knowledge_results if r.get("status") == "ok" and r.get("knowledgeId")}
        if observed != expected:
            raise RuntimeError(f"Knowledge reconciliation mismatch: missing={sorted(expected - observed)}, extra={sorted(observed - expected)}")
        completed = True
    finally:
        report = {"gateway": gateway.BASE_URL, "partition": gateway.PART_ID, "results": results,
                  "completed": completed, "knowledge_results": knowledge_results,
                  "calls": len(calls), "failed_calls": sum(c["status"] == "fail" for c in calls),
                  "scope": "Normalized products.json, flight_products.json, discount_prompts.json; prerequisite segments from parent fixture. XLSX source files unchanged; flight_catalog_refs.json contains unmatched search evidence, no refs to replay."}
        (OUTPUT / "travel_fixture_results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
