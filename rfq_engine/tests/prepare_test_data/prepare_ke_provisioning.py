#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Provision the knowledge_engine (KE) assets the RFQ Engine integrates with
(Phase 0, task T0.2 of the KGE→KE migration plan).

Per staging tenant (``endpoint_id#part_id``), this script:

    1. Ensures a knowledge domain exists (default code ``rfq-catalog``,
       ``domain_type: OWN``) via KE ``createKnowledgeDomain``.
    2. Ensures one knowledge type per RFQ entity type (``rfq-item``,
       ``rfq-provider-item``, ``rfq-request``, ``rfq-quote``, ``rfq-bundle``,
       ``rfq-discount-prompt``) via KE ``createKnowledgeType``.
    3. Prints the ``knowledge_engine_ingest`` settings block (with the
       returned UUID ids) to paste into the RFQ deployment settings, plus
       the matching ``tests/.env`` lines.
    4. Writes ``ke_provisioning.json`` next to this script for auditing.

Idempotent: existing domains/types (matched by their string codes) are
reused, never duplicated. RFQ never creates domains/types at runtime —
this script is the explicit provisioning step the handler's
``configuration_error`` fail-fast (risk R2) refers to.

Invokes KE in-process through ``silvaengine_utility.Invoker``'s
``invoke_funct_on_local`` (funct ``knowledge_engine_graphql``), mirroring
``handlers/catalog/handler.py``.

Usage::

    python rfq_engine/tests/prepare_test_data/prepare_ke_provisioning.py

Required env (tests/.env or shell)::

    endpoint_id, part_id          # tenant
    base_dir                      # silvaengine source root
    KE_OPERATOR_ID                # user id/sub for KE audit + operator checks
    KE_TENANT_ID                  # optional tenant_id claim (UUID)

Optional env::

    KE_DOMAIN_CODE=rfq-catalog
    KE_DOMAIN_NAME=RFQ Catalog
    KE_DOMAIN_TYPE=OWN             # OWN | SHARED | PUBLIC
    KE_ENTITY_TYPES=item,provider_item,request,quote,bundle,discount_prompt
    KE_PERMISSIONS=knowledge:admin  # permission claim for the operator

Emits (copy into tests/.env or deployment settings)::

    ke_domain_id=<uuid>
    ke_type_item=<uuid>
    ke_type_provider_item=<uuid>
    ...
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
# knowledge_engine lives in the banyanos repo next to silvaengine repos.
KE_BASE_DIR = os.getenv("ke_base_dir") or os.path.join(
    os.path.dirname(BASE_DIR), "banyanos", "knowledge_engine"
)
if os.path.isdir(KE_BASE_DIR) and KE_BASE_DIR not in sys.path:
    sys.path.insert(0, KE_BASE_DIR)

from silvaengine_utility import Invoker  # noqa: E402

from _backend_setting import build_setting  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("prepare_ke_provisioning")

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(HERE, "ke_provisioning.json")

DOMAIN_CODE = os.getenv("KE_DOMAIN_CODE", "rfq-catalog")
DOMAIN_NAME = os.getenv("KE_DOMAIN_NAME", "RFQ Catalog")
DOMAIN_TYPE = os.getenv("KE_DOMAIN_TYPE", "OWN")
ENTITY_TYPES = [
    e.strip()
    for e in os.getenv(
        "KE_ENTITY_TYPES",
        "item,provider_item,request,quote,bundle,discount_prompt",
    ).split(",")
    if e.strip()
]
OPERATOR_ID = os.getenv("KE_OPERATOR_ID") or os.getenv("operator_id") or "admin"
TENANT_ID = os.getenv("KE_TENANT_ID") or None
PERMISSIONS = os.getenv("KE_PERMISSIONS", "knowledge:admin")

# Human-readable names for the per-entity knowledge types.
TYPE_NAMES = {
    "item": "RFQ Item",
    "provider_item": "RFQ Provider Item",
    "request": "RFQ Request",
    "quote": "RFQ Quote",
    "bundle": "RFQ Bundle",
    "discount_prompt": "RFQ Discount Prompt",
}


SETTING = build_setting()
# In-process KE invocation (same funct shape the RFQ catalog handler uses).
SETTING.setdefault("functs_on_local", {})["knowledge_engine_graphql"] = {
    "module_name": "knowledge_engine",
    "class_name": "KnowledgeEngine",
}


# --- GraphQL documents ------------------------------------------------------ #

_LIST_DOMAINS_QUERY = """
query KnowledgeDomains($first: Int, $filter: KnowledgeDomainFilterInput) {
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


# --- Invocation ------------------------------------------------------------- #


def _claims_context() -> Dict[str, Any]:
    """Identity claims forwarded to the KE GraphQL context."""
    context: Dict[str, Any] = {"user": {"sub": OPERATOR_ID}}
    if TENANT_ID:
        context["tenant_id"] = TENANT_ID
    context["permissions"] = PERMISSIONS
    return context


def invoke(query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call knowledge_engine_graphql through Invoker.invoke_funct_on_local."""
    # Mirror the R4 mitigation from handlers/catalog/handler.py: strip
    # RFQ backend keys so a first-call KE Config init is not misconfigured.
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
            endpoint_id=SETTING.get("endpoint_id"),
            part_id=SETTING.get("part_id"),
            context=_claims_context(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("KE invocation failed: %s", exc)
        return None


# --- Provisioning steps ------------------------------------------------------ #


def ensure_domain() -> Optional[Dict[str, Any]]:
    """Find or create the RFQ catalog domain; return its KE node."""
    data = invoke(
        _LIST_DOMAINS_QUERY,
        {"first": 100, "filter": {"keyword": DOMAIN_CODE}},
    )
    edges = ((data or {}).get("knowledgeDomains") or {}).get("edges") or []
    for edge in edges:
        node = edge.get("node") or {}
        if node.get("domainId") == DOMAIN_CODE:
            logger.info(
                "domain %r exists (id=%s, status=%s) — reusing",
                DOMAIN_CODE,
                node.get("id"),
                node.get("status"),
            )
            return node

    logger.info("creating knowledge domain %r (type=%s)", DOMAIN_CODE, DOMAIN_TYPE)
    result = invoke(
        _CREATE_DOMAIN_MUTATION,
        {
            "input": {
                "domainType": DOMAIN_TYPE,
                "domainId": DOMAIN_CODE,
                "name": DOMAIN_NAME,
                "description": (
                    "RFQ Engine catalog and transactional knowledge "
                    "(auto-provisioned by prepare_ke_provisioning.py)"
                ),
            },
            "idempotencyKey": f"rfq-provision:domain:{DOMAIN_CODE}",
        },
    )
    node = (result or {}).get("createKnowledgeDomain")
    if not node:
        logger.error("createKnowledgeDomain returned no payload")
        return None
    logger.info("domain created: id=%s", node.get("id"))
    return node


def ensure_type(entity_type: str) -> Optional[Dict[str, Any]]:
    """Find or create the knowledge type for one RFQ entity type."""
    code = f"rfq-{entity_type.replace('_', '-')}"
    data = invoke(_LIST_TYPES_QUERY, {"filter": {"code": code}, "first": 5})
    edges = ((data or {}).get("knowledgeTypes") or {}).get("edges") or []
    for edge in edges:
        node = edge.get("node") or {}
        if node.get("code") == code:
            logger.info(
                "type %r exists (id=%s, status=%s) — reusing",
                code,
                node.get("id"),
                node.get("status"),
            )
            return node

    logger.info("creating knowledge type %r", code)
    result = invoke(
        _CREATE_TYPE_MUTATION,
        {
            "input": {
                "code": code,
                "name": TYPE_NAMES.get(entity_type, code),
                "description": (
                    f"RFQ {entity_type} entities ingested by the RFQ "
                    "knowledge-ingestion bridge"
                ),
            },
            "idempotencyKey": f"rfq-provision:type:{code}",
        },
    )
    node = (result or {}).get("createKnowledgeType")
    if not node:
        logger.error("createKnowledgeType returned no payload for %r", code)
        return None
    logger.info("type created: code=%s id=%s", code, node.get("id"))
    return node


# --- Output ------------------------------------------------------------------ #


def write_outputs(domain: Dict[str, Any], types: Dict[str, Dict[str, Any]]) -> None:
    domain_id = str(domain.get("id"))
    type_ids = {entity: str(node.get("id")) for entity, node in types.items()}

    record = {
        "domain": {"id": domain_id, "code": DOMAIN_CODE},
        "types": {
            entity: {"id": type_ids[entity], "code": f"rfq-{entity.replace('_', '-')}"}
            for entity in types
        },
        "knowledge_engine_ingest": {
            "domain_id": domain_id,
            "type_ids": type_ids,
            "namespace": "KE",
            "sync_item_catalog_ref": True,
        },
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    logger.info("wrote %s", OUTPUT_FILE)

    print("\n=== knowledge_engine_ingest settings block (deployment settings) ===")
    print(json.dumps(record["knowledge_engine_ingest"], indent=2))
    print("\n=== tests/.env lines ===")
    print(f"ke_domain_id={domain_id}")
    for entity, type_id in type_ids.items():
        print(f"ke_type_{entity}={type_id}")
    print()


def generate() -> int:
    if not SETTING.get("endpoint_id") or not SETTING.get("part_id"):
        raise RuntimeError(
            "endpoint_id and part_id must be set in tests/.env before running"
        )

    domain = ensure_domain()
    if not domain:
        return 1

    types: Dict[str, Dict[str, Any]] = {}
    failures: List[str] = []
    for entity_type in ENTITY_TYPES:
        node = ensure_type(entity_type)
        if node:
            types[entity_type] = node
        else:
            failures.append(entity_type)

    write_outputs(domain, types)

    if failures:
        logger.error("provisioning failed for entity types: %s", ", ".join(failures))
        return 1

    logger.info(
        "--- Provisioning complete: domain=%s, %d types ---",
        DOMAIN_CODE,
        len(types),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(generate())