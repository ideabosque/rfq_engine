#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Shadow-compare `inquire_catalog` across the KGE and knowledge_engine
backends (migration plan T4.1 — dual-run flag / shadow comparison).

For each test inquiry, runs the exact same GraphQL operation twice — once
with `catalog_knowledge_backend: "kge"` and once with
`"knowledge_engine"` — and records:

  * per-backend in-band error codes,
  * payload top-level key sets (contract compatibility — both backends
    must expose the legacy ``{results, total, ...}`` envelope for
    semantic-mode inquiries),
  * result counts (coverage — the KE total should be >= the KGE total
    after backfill; shortfalls are flagged for soak review).

Writes ``shadow_report.json`` with a per-case table and a summary verdict
for the T4.1 acceptance: "shadow log shows >= 1:1 result coverage with
no contract breaks".

Usage::

    python rfq_engine/tests/prepare_test_data/shadow_compare_catalog_inquiry.py

Env (tests/.env)::

    endpoint_id, part_id, base_dir
    SHADOW_QUERIES_FILE=<json>   # optional: [{"namespace": "...", "query": {...}}, ...]
    SHADOW_MAX_CASES=20          # cap on built-in default cases
    SHADOW_COVERAGE_RATIO=1.0    # flag ke_total < kge_total * ratio as shortfall
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
logger = logging.getLogger("shadow_compare_catalog_inquiry")

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(HERE, "shadow_report.json")

COVERAGE_RATIO = float(os.getenv("SHADOW_COVERAGE_RATIO", "1.0"))
MAX_CASES = int(os.getenv("SHADOW_MAX_CASES", "20"))

_BASE_SETTING = build_setting()
_BASE_SETTING.setdefault("functs_on_local", {})
# Both backends must be routable in-process for a shadow run.
_BASE_SETTING["functs_on_local"]["knowledge_engine_graphql"] = {
    "module_name": "knowledge_engine",
    "class_name": "KnowledgeEngine",
}
_BASE_SETTING["functs_on_local"]["knowledge_graph_graphql"] = {
    "module_name": "knowledge_graph_engine",
    "class_name": "KnowledgeGraphEngine",
}

# Default inquiries: a smoke spread over the catalog. Override with
# SHADOW_QUERIES_FILE for tenant-specific soak queries.
DEFAULT_CASES = [
    {"namespace": "KE", "query": {"queryText": "hotel", "searchMode": "semantic", "limit": 10}},
    {"namespace": "KE", "query": {"queryText": "flight", "searchMode": "semantic", "limit": 10}},
    {"namespace": "KE", "query": {"queryText": "transfer", "searchMode": "semantic", "limit": 10}},
    {"namespace": "KE", "query": {"queryText": "activity", "searchMode": "semantic", "limit": 10}},
    {"namespace": "KE", "query": {"queryText": "banquet", "searchMode": "semantic", "limit": 10}},
]

# Contract keys that must be present in every semantic-mode payload
# regardless of backend (the legacy KGE envelope).
_REQUIRED_PAYLOAD_KEYS = ("results", "total")


_INQUIRE_CATALOG_QUERY = """
query InquireCatalog($namespace: String, $nodeId: String, $query: JSONCamelCase) {
    inquireCatalog(namespace: $namespace, nodeId: $nodeId, query: $query) {
        namespace
        nodeId
        payload
        fetchedAt
        errorCode
        errorMessage
    }
}
"""


def load_cases() -> List[Dict[str, Any]]:
    queries_file = os.getenv("SHADOW_QUERIES_FILE")
    if queries_file and os.path.isfile(queries_file):
        with open(queries_file, "r", encoding="utf-8") as f:
            cases = json.load(f)
        if isinstance(cases, list) and cases:
            logger.info("loaded %d shadow cases from %s", len(cases), queries_file)
            return cases
    logger.info("using built-in default shadow cases (cap %d)", MAX_CASES)
    return DEFAULT_CASES[:MAX_CASES]


def inquire(backend: str, case: Dict[str, Any]) -> Dict[str, Any]:
    """Run one inquire_catalog against the selected backend."""
    setting = dict(_BASE_SETTING)
    setting["catalog_knowledge_backend"] = backend
    try:
        data = Invoker.invoke_funct_on_local(
            logger,
            setting,
            "rfq_graphql",
            query=_INQUIRE_CATALOG_QUERY,
            variables={
                "namespace": case.get("namespace"),
                "nodeId": case.get("nodeId"),
                "query": case.get("query"),
            },
            endpoint_id=setting.get("endpoint_id"),
            part_id=setting.get("part_id"),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error_code": "invocation_failed", "error_message": str(exc)[:500]}
    result = (data or {}).get("inquireCatalog") or {}
    return result


def summarize(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = result.get("payload") if isinstance(result, dict) else None
    return {
        "error_code": result.get("errorCode"),
        "error_message": (result.get("errorMessage") or None),
        "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "total": payload.get("total") if isinstance(payload, dict) else None,
        "results_count": (
            len(payload.get("results") or [])
            if isinstance(payload, dict) and isinstance(payload.get("results"), list)
            else None
        ),
    }


def run_case(index: int, case: Dict[str, Any]) -> Dict[str, Any]:
    query = case.get("query") or {}
    label = query.get("queryText") or case.get("nodeId") or f"case-{index}"
    logger.info("[%d/%s] backend=kge ...", index + 1, label)
    kge = summarize(inquire("kge", case))
    logger.info("[%d/%s] backend=knowledge_engine ...", index + 1, label)
    ke = summarize(inquire("knowledge_engine", case))

    kge_keys = set(kge["payload_keys"])
    ke_keys = set(ke["payload_keys"])
    required = set(_REQUIRED_PAYLOAD_KEYS)
    contract_ok = required.issubset(kge_keys) and required.issubset(ke_keys)

    coverage_note = "n/a"
    coverage_ok: Optional[bool] = None
    if (
        isinstance(kge["total"], int)
        and isinstance(ke["total"], int)
        and kge["total"] > 0
    ):
        ratio = ke["total"] / kge["total"]
        coverage_ok = ratio >= COVERAGE_RATIO
        coverage_note = f"ke/kge total ratio = {ratio:.2f} (threshold {COVERAGE_RATIO})"

    return {
        "label": label,
        "namespace": case.get("namespace"),
        "query": query,
        "kge": kge,
        "knowledge_engine": ke,
        "contract_ok": contract_ok,
        "coverage_ok": coverage_ok,
        "coverage_note": coverage_note,
    }


def generate() -> Dict[str, Any]:
    if not _BASE_SETTING.get("endpoint_id") or not _BASE_SETTING.get("part_id"):
        raise RuntimeError(
            "endpoint_id and part_id must be set in tests/.env before running"
        )

    cases = load_cases()
    rows = [run_case(i, case) for i, case in enumerate(cases)]

    contract_breaks = [r["label"] for r in rows if not r["contract_ok"]]
    coverage_shortfalls = [
        r["label"] for r in rows if r["coverage_ok"] is False
    ]
    error_diffs = [
        r["label"]
        for r in rows
        if (r["kge"]["error_code"] is None) != (r["knowledge_engine"]["error_code"] is None)
    ]

    return {
        "coverageRatioThreshold": COVERAGE_RATIO,
        "cases": rows,
        "summary": {
            "cases": len(rows),
            "contract_breaks": contract_breaks,
            "coverage_shortfalls": coverage_shortfalls,
            "error_presence_diffs": error_diffs,
            "verdict": (
                "PASS"
                if not contract_breaks and not error_diffs and not coverage_shortfalls
                else "REVIEW"
            ),
        },
    }


def write_output(report: Dict[str, Any]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("wrote %s", OUTPUT_FILE)
    summary = report["summary"]
    logger.info(
        "--- Shadow verdict: %s | cases=%d contract_breaks=%d coverage_shortfalls=%d error_diffs=%d ---",
        summary["verdict"],
        summary["cases"],
        len(summary["contract_breaks"]),
        len(summary["coverage_shortfalls"]),
        len(summary["error_presence_diffs"]),
    )


if __name__ == "__main__":
    result = generate()
    write_output(result)
    logger.info("--- Done ---")