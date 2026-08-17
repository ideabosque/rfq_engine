#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Seed product data for the RFQ Engine — domain-agnostic and configurable.

Looks up an existing ``Segment`` (run ``prepare_segments_and_contacts.py``
first) and generates a coherent product catalog across seven tables:

    Item                 — a product/service
    ProviderItem         — a supplier's offering of that product
    CancellationPolicy   — refund/cancellation tiers
    ProviderItemBatch    — a specific inventory lot with service window
    ItemPriceTier        — pricing tiers per segment
    Bundle               — reusable multi-component package template
    BundleComponent      — components inside the package template

The domain is driven by ``SEED_PRODUCT_DOMAIN`` env var. Built-in domains:

    flight   — flight cabin products (IATA codes, airlines, cabin classes)
    hotel    — hotel room-night products (cities, hotel chains, room types)
    generic  — generic B2B products (product categories, suppliers, tiers)

Output JSON is written to ``<SEED_PRODUCT_OUTPUT_DIR>/products.json``.
By default the output directory is the script's own directory, but you can
set ``SEED_PRODUCT_OUTPUT_DIR=dds`` or ``SEED_PRODUCT_OUTPUT_DIR=travel``
to store domain-specific data in subfolders.

Usage::

    # Flight domain (default), output to top level
    python rfq_engine/tests/prepare_test_data/prepare_products.py

    # Hotel domain, output to travel/ subfolder
    SEED_PRODUCT_DOMAIN=hotel SEED_PRODUCT_OUTPUT_DIR=travel \\
        python rfq_engine/tests/prepare_test_data/prepare_products.py

    # Generic B2B, output to dds/ subfolder
    SEED_PRODUCT_DOMAIN=generic SEED_PRODUCT_OUTPUT_DIR=dds \\
        python rfq_engine/tests/prepare_test_data/prepare_products.py

Configurable via env vars::

    SEED_PRODUCT_DOMAIN=flight        # flight | hotel | generic
    SEED_PRODUCT_OUTPUT_DIR=.         # subfolder for output JSON
    SEED_NUM_ROUTES=5                 # number of Item rows
    SEED_BATCHES_PER_ROUTE=2          # ProviderItemBatch rows per item
    SEED_NUM_BUNDLES=2               # package templates to create
    SEED_BUNDLE_SIZE=3               # max components per bundle
    SEED_PRODUCT_SEGMENT_UUID=...    # pin a specific segment
"""
from __future__ import annotations

__author__ = "bibow"

import json
import logging
import os
import random
import sys
from datetime import timedelta

import pendulum
from dotenv import load_dotenv

TESTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(TESTS_DIR, ".env"))

BASE_DIR = os.getenv("base_dir") or os.path.abspath(
    os.path.join(TESTS_DIR, "..", "..")
)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "silvaengine_utility"))
sys.path.insert(1, os.path.join(BASE_DIR, "silvaengine_dynamodb_base"))
sys.path.insert(2, os.path.join(BASE_DIR, "silvaengine_constants"))
sys.path.insert(3, os.path.join(BASE_DIR, "rfq_engine"))

from rfq_engine import RFQEngine  # noqa: E402
from silvaengine_utility.serializer import Serializer  # noqa: E402

try:
    from faker import Faker
except ModuleNotFoundError:
    sys.exit("The 'faker' package is not installed. Install it with: pip install faker")


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("prepare_products")
fake = Faker()

UPDATED_BY = "prepare_products"
DOMAIN = os.getenv("SEED_PRODUCT_DOMAIN", "flight")
# Default output subfolder matches the domain name (dds, travel, etc.)
# Override with SEED_PRODUCT_OUTPUT_DIR if you want a different subfolder or "." for top level.
DEFAULT_OUTPUT_DIR = "dds" if DOMAIN == "generic" else DOMAIN
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), os.getenv("SEED_PRODUCT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "products.json")

NUM_ROUTES = int(os.getenv("SEED_NUM_ROUTES", "5"))
BATCHES_PER_ROUTE = int(os.getenv("SEED_BATCHES_PER_ROUTE", "2"))
NUM_BUNDLES = int(os.getenv("SEED_NUM_BUNDLES", "2"))
BUNDLE_SIZE = max(2, int(os.getenv("SEED_BUNDLE_SIZE", "3")))
PINNED_SEGMENT_UUID = os.getenv("SEED_PRODUCT_SEGMENT_UUID")

from _backend_setting import build_setting  # noqa: E402
SETTING = build_setting()


# ---------------------------------------------------------------------------
# Domain configurations
# ---------------------------------------------------------------------------

DOMAIN_CONFIGS: dict[str, dict] = {
    "flight": {
        "item_type": "flight",
        "uom": "seat",
        "pricing_mode": "per_pax_type",
        "bundle_type": "flight_itinerary",
        "component_role": "flight_leg",
        "locations": [
            ("JFK", "New York"), ("LAX", "Los Angeles"), ("ORD", "Chicago"),
            ("SFO", "San Francisco"), ("ATL", "Atlanta"), ("DFW", "Dallas"),
            ("SEA", "Seattle"), ("MIA", "Miami"), ("BOS", "Boston"),
            ("LHR", "London"), ("CDG", "Paris"), ("NRT", "Tokyo"),
            ("SIN", "Singapore"), ("HKG", "Hong Kong"), ("SYD", "Sydney"),
        ],
        "suppliers": [
            ("AA", "American Airlines"), ("DL", "Delta Air Lines"),
            ("UA", "United Airlines"), ("BA", "British Airways"),
            ("AF", "Air France"), ("LH", "Lufthansa"),
            ("SQ", "Singapore Airlines"), ("CX", "Cathay Pacific"),
            ("JL", "Japan Airlines"), ("QF", "Qantas"),
        ],
        "variants": [
            {"name": "Economy", "base_price": 250.0},
            {"name": "Premium Economy", "base_price": 450.0},
            {"name": "Business", "base_price": 1800.0},
            {"name": "First", "base_price": 4500.0},
        ],
        "pax_types": [("adult", 1.00), ("child", 0.75), ("infant", 0.10)],
        "supplier_prefix": "AIRLINE",
        "batch_id_prefix": "FLT",
        "batch_capacity_range": (120, 240),
        "intl_codes": {"LHR", "CDG", "NRT", "SIN", "HKG", "SYD"},
        "duration_range_domestic": (1.5, 6.0),
        "duration_range_intl": (7.0, 14.0),
    },
    "hotel": {
        "item_type": "hotel",
        "uom": "night",
        "pricing_mode": "occupancy",
        "bundle_type": "hotel_package",
        "component_role": "hotel_stay",
        "locations": [
            ("NYC", "New York"), ("LAX", "Los Angeles"), ("CHI", "Chicago"),
            ("SFO", "San Francisco"), ("MIA", "Miami"), ("BOS", "Boston"),
            ("LON", "London"), ("PAR", "Paris"), ("TYO", "Tokyo"),
            ("SIN", "Singapore"), ("HKG", "Hong Kong"), ("SYD", "Sydney"),
        ],
        "suppliers": [
            ("HT", "Hilton"), ("MR", "Marriott"), ("HY", "Hyatt"),
            ("IC", "InterContinental"), ("SP", "Starwood"),
            ("4S", "Four Seasons"), ("RC", "Ritz-Carlton"),
            ("SH", "Shangri-La"), ("WH", "W Hotels"), ("NB", "Nobu"),
        ],
        "variants": [
            {"name": "Standard Room", "base_price": 150.0},
            {"name": "Deluxe Room", "base_price": 280.0},
            {"name": "Suite", "base_price": 650.0},
            {"name": "Presidential Suite", "base_price": 1800.0},
        ],
        "pax_types": [("adult", 1.00)],
        "supplier_prefix": "HOTEL",
        "batch_id_prefix": "HTL",
        "batch_capacity_range": (20, 80),
        "intl_codes": {"LON", "PAR", "TYO", "SIN", "HKG", "SYD"},
        "duration_range_domestic": (1.0, 5.0),
        "duration_range_intl": (3.0, 10.0),
    },
    "generic": {
        "item_type": "product",
        "uom": "each",
        "pricing_mode": "unit",
        "bundle_type": "product_bundle",
        "component_role": "product_component",
        "locations": [
            ("US-W", "US West"), ("US-E", "US East"), ("EU", "Europe"),
            ("APAC", "Asia Pacific"), ("LATAM", "Latin America"),
        ],
        "suppliers": [
            ("SUP-A", "Supplier Alpha"), ("SUP-B", "Supplier Beta"),
            ("SUP-C", "Supplier Gamma"), ("SUP-D", "Supplier Delta"),
            ("SUP-E", "Supplier Epsilon"), ("SUP-F", "Supplier Zeta"),
            ("SUP-G", "Supplier Eta"), ("SUP-H", "Supplier Theta"),
            ("SUP-I", "Supplier Iota"), ("SUP-J", "Supplier Kappa"),
        ],
        "variants": [
            {"name": "Standard", "base_price": 50.0},
            {"name": "Premium", "base_price": 120.0},
            {"name": "Professional", "base_price": 350.0},
            {"name": "Enterprise", "base_price": 850.0},
        ],
        "pax_types": [("unit", 1.00)],
        "supplier_prefix": "SUPPLIER",
        "batch_id_prefix": "BATCH",
        "batch_capacity_range": (50, 500),
        "intl_codes": {"EU", "APAC", "LATAM"},
        "duration_range_domestic": (1.0, 3.0),
        "duration_range_intl": (5.0, 15.0),
    },
}

CONFIG = DOMAIN_CONFIGS.get(DOMAIN, DOMAIN_CONFIGS["generic"])


# --- GraphQL --------------------------------------------------------------- #

SEGMENT_LIST_QUERY = """
query SegmentList($limit: Int, $offset: Int) {
    segmentList(limit: $limit, pageNumber: $offset) {
        segmentList { segmentUuid segmentName }
        total
    }
}
"""

ITEM_MUTATION = """
mutation InsertUpdateItem($type:String,$name:String,$desc:String,$mode:String,$uom:String,$extId:String,$by:String!){
    insertUpdateItem(itemType:$type,itemName:$name,itemDescription:$desc,pricingMode:$mode,uom:$uom,itemExternalId:$extId,updatedBy:$by){item{itemUuid}}
}
"""

PROVIDER_ITEM_MUTATION = """
mutation InsertUpdateProviderItem($iid:String!,$extId:String,$providerExt:String,$price:SafeFloat,$mode:String,$spec:JSONCamelCase,$by:String!){
    insertUpdateProviderItem(itemUuid:$iid,providerCorpExternalId:$extId,providerItemExternalId:$providerExt,basePricePerUom:$price,availabilityMode:$mode,itemSpec:$spec,updatedBy:$by){providerItem{providerItemUuid}}
}
"""

CANCELLATION_POLICY_MUTATION = """
mutation InsertUpdateCancellationPolicy($label:String,$desc:String,$tiers:JSONCamelCase,$provider:String,$by:String!){
    insertUpdateCancellationPolicy(label:$label,description:$desc,tiers:$tiers,providerItemUuid:$provider,updatedBy:$by){cancellationPolicy{policyUuid}}
}
"""

PROVIDER_ITEM_BATCH_MUTATION = """
mutation InsertUpdateProviderItemBatch($pid:String!,$iid:String!,$bno:String!,$prod:DateTime,$exp:DateTime,$start:DateTime,$end:DateTime,$cost:SafeFloat,$freight:SafeFloat,$addl:SafeFloat,$qty:SafeFloat,$cur:String,$polUuid:String,$by:String!){
    insertUpdateProviderItemBatch(providerItemUuid:$pid,itemUuid:$iid,batchNo:$bno,producedAt:$prod,expiredAt:$exp,serviceStartAt:$start,serviceEndAt:$end,costPerUom:$cost,freightCostPerUom:$freight,additionalCostPerUom:$addl,availabilityQty:$qty,inStock:true,currency:$cur,cancellationPolicyUuid:$polUuid,updatedBy:$by){providerItemBatch{batchNo availabilityQty}}
}
"""

ITEM_PRICE_TIER_MUTATION = """
mutation InsertUpdateItemPriceTier($iid:String!,$pid:String,$sid:String,$qty:SafeFloat,$price:SafeFloat,$pax:String,$cur:String,$stat:String,$by:String!){
    insertUpdateItemPriceTier(itemUuid:$iid,providerItemUuid:$pid,segmentUuid:$sid,quantityGreaterThen:$qty,pricePerUom:$price,paxType:$pax,currency:$cur,status:$stat,updatedBy:$by){itemPriceTier{itemPriceTierUuid}}
}
"""

BUNDLE_MUTATION = """
mutation InsertUpdateBundle($code:String,$name:String,$type:String,$desc:String,$extra:JSONCamelCase,$stat:String,$by:String!){
    insertUpdateBundle(bundleCode:$code,bundleName:$name,bundleType:$type,description:$desc,extra:$extra,status:$stat,updatedBy:$by){bundle{bundleUuid bundleCode bundleName}}
}
"""

BUNDLE_COMPONENT_MUTATION = """
mutation InsertUpdateBundleComponent($bundle:String,$item:String,$provider:String,$role:String,$required:Boolean,$qty:SafeFloat,$order:SafeFloat,$extra:JSONCamelCase,$stat:String,$by:String!){
    insertUpdateBundleComponent(bundleUuid:$bundle,itemUuid:$item,providerItemUuid:$provider,componentRole:$role,required:$required,defaultQty:$qty,sortOrder:$order,extra:$extra,status:$stat,updatedBy:$by){bundleComponent{bundleComponentUuid bundleUuid itemUuid providerItemUuid componentRole}}
}
"""


# --- Helpers ---------------------------------------------------------------- #

def create_engine() -> RFQEngine:
    engine = RFQEngine(logger, **SETTING)
    setattr(engine, "__is_real__", True)
    return engine


def run_graphql(engine: RFQEngine, query: str, variables: dict) -> dict | None:
    try:
        response = engine.rfq_graphql(
            query=query, variables=variables,
            endpoint_id=SETTING["endpoint_id"], part_id=SETTING["part_id"],
        )
    except Exception:
        logger.exception("GraphQL execution failed")
        return None
    parsed = Serializer.json_loads(response) if isinstance(response, (str, bytes)) else response
    if isinstance(parsed, dict) and isinstance(parsed.get("body"), str):
        try:
            parsed = Serializer.json_loads(parsed["body"])
        except Exception:
            pass
    if not isinstance(parsed, dict):
        logger.error("Unexpected response: %s", parsed)
        return None
    if parsed.get("errors"):
        logger.error("GraphQL error: %s", Serializer.json_dumps(parsed["errors"]))
        return None
    return parsed.get("data", parsed)


def lookup_segment_uuid(engine: RFQEngine) -> str:
    if PINNED_SEGMENT_UUID:
        return PINNED_SEGMENT_UUID
    data = run_graphql(engine, SEGMENT_LIST_QUERY, {"limit": 10, "offset": 1})
    if not data:
        raise RuntimeError("Could not query segmentList — run prepare_segments_and_contacts.py first")
    segments = (data.get("segmentList") or {}).get("segmentList") or []
    if not segments:
        raise RuntimeError("No segments found. Run prepare_segments_and_contacts.py first.")
    return segments[0]["segmentUuid"]


def pick_route() -> tuple[tuple[str, str], tuple[str, str]]:
    return tuple(random.sample(CONFIG["locations"], 2))


def pick_variant() -> dict:
    return random.choice(CONFIG["variants"])


def pick_supplier() -> tuple[str, str]:
    return random.choice(CONFIG["suppliers"])


def batch_id(supplier_code: str) -> str:
    return f"{CONFIG['batch_id_prefix']}{supplier_code}{random.randint(100, 9999)}"


def service_duration_hours(origin_code: str, dest_code: str) -> float:
    intl = {origin_code, dest_code} & CONFIG["intl_codes"]
    if intl:
        return random.uniform(*CONFIG["duration_range_intl"])
    return random.uniform(*CONFIG["duration_range_domestic"])


# --- Seeders ---------------------------------------------------------------- #

def seed_cancellation_policy(engine: RFQEngine, variant_name: str) -> dict | None:
    label = f"{variant_name} Cancellation"
    tiers = {"tiers": [
        {"hours_before_service_gte": 168, "refund_pct": 1.0},
        {"hours_before_service_gte": 24, "refund_pct": 0.5},
        {"hours_before_service_gte": 0, "refund_pct": 0.0},
    ]}
    data = run_graphql(engine, CANCELLATION_POLICY_MUTATION, {
        "label": label, "desc": fake.sentence(nb_words=12),
        "tiers": tiers, "provider": None, "by": UPDATED_BY,
    })
    if not data:
        return None
    uuid_ = data["insertUpdateCancellationPolicy"]["cancellationPolicy"]["policyUuid"]
    return {"policyUuid": uuid_, "label": label, "tiers": tiers}


def seed_item(engine: RFQEngine, route: tuple, variant: dict) -> dict | None:
    (orig_code, orig_city), (dest_code, dest_city) = route
    name = f"{CONFIG['item_type'].title()} {orig_code}->{dest_code} {variant['name']}"
    desc = f"{variant['name']} {CONFIG['item_type']} from {orig_city} ({orig_code}) to {dest_city} ({dest_code})."
    ext_id = f"{CONFIG['item_type'].upper()}-{orig_code}-{dest_code}-{variant['name'][:3].upper()}"
    data = run_graphql(engine, ITEM_MUTATION, {
        "type": CONFIG["item_type"], "name": name, "desc": desc,
        "mode": CONFIG["pricing_mode"], "uom": CONFIG["uom"],
        "extId": ext_id, "by": UPDATED_BY,
    })
    if not data:
        return None
    uuid_ = data["insertUpdateItem"]["item"]["itemUuid"]
    return {"itemUuid": uuid_, "itemType": CONFIG["item_type"], "itemName": name,
            "itemDescription": desc, "pricingMode": CONFIG["pricing_mode"],
            "uom": CONFIG["uom"], "itemExternalId": ext_id}


def seed_provider_item(engine: RFQEngine, item_uuid: str, supplier: tuple, variant: dict, route: tuple) -> dict | None:
    code, name = supplier
    (orig_code, _), (dest_code, _) = route
    spec = {"supplier_code": code, "supplier_name": name, "variant": variant["name"],
            "origin": orig_code, "destination": dest_code}
    ext = f"{code}-{orig_code}-{dest_code}-{variant['name'][:3].upper()}"
    corp = f"{CONFIG['supplier_prefix']}-{code}"
    data = run_graphql(engine, PROVIDER_ITEM_MUTATION, {
        "iid": item_uuid, "extId": corp, "providerExt": ext,
        "price": variant["base_price"], "mode": "require_hold",
        "spec": spec, "by": UPDATED_BY,
    })
    if not data:
        return None
    uuid_ = data["insertUpdateProviderItem"]["providerItem"]["providerItemUuid"]
    return {"providerItemUuid": uuid_, "itemUuid": item_uuid,
            "providerCorpExternalId": corp, "providerItemExternalId": ext,
            "basePricePerUom": variant["base_price"], "availabilityMode": "require_hold",
            "itemSpec": spec}


def seed_batch(engine: RFQEngine, item_uuid: str, provider_item_uuid: str,
               supplier: tuple, route: tuple, variant: dict, policy_uuid: str, days_ahead: int) -> dict | None:
    code, _ = supplier
    (orig_code, _), (dest_code, _) = route
    bno = f"{batch_id(code)}-{pendulum.now('UTC').add(days=days_ahead).format('YYYYMMDD')}"
    start = pendulum.now("UTC").add(days=days_ahead).at(random.randint(6, 22), random.choice([0, 15, 30, 45]))
    end = start + timedelta(hours=service_duration_hours(orig_code, dest_code))
    qty = random.randint(*CONFIG["batch_capacity_range"])
    cost = round(variant["base_price"] * 0.55, 2)
    data = run_graphql(engine, PROVIDER_ITEM_BATCH_MUTATION, {
        "pid": provider_item_uuid, "iid": item_uuid, "bno": bno,
        "prod": start.subtract(days=180).to_iso8601_string(),
        "exp": end.to_iso8601_string(),
        "start": start.to_iso8601_string(), "end": end.to_iso8601_string(),
        "cost": cost, "freight": 0.0,
        "addl": round(random.uniform(15.0, 60.0), 2),
        "qty": float(qty), "cur": "USD", "polUuid": policy_uuid, "by": UPDATED_BY,
    })
    if not data:
        return None
    return {"providerItemUuid": provider_item_uuid, "batchNo": bno, "itemUuid": item_uuid,
            "serviceStartAt": start.to_iso8601_string(), "serviceEndAt": end.to_iso8601_string(),
            "availabilityQty": qty, "currency": "USD", "cancellationPolicyUuid": policy_uuid}


def seed_price_tiers(engine: RFQEngine, item_uuid: str, provider_item_uuid: str,
                     segment_uuid: str, variant: dict) -> list[dict]:
    tiers = []
    for pax_type, multiplier in CONFIG["pax_types"]:
        price = round(variant["base_price"] * multiplier, 2)
        data = run_graphql(engine, ITEM_PRICE_TIER_MUTATION, {
            "iid": item_uuid, "pid": provider_item_uuid, "sid": segment_uuid,
            "qty": 0.0, "price": price, "pax": pax_type,
            "cur": "USD", "stat": "active", "by": UPDATED_BY,
        })
        if not data:
            continue
        uuid_ = data["insertUpdateItemPriceTier"]["itemPriceTier"]["itemPriceTierUuid"]
        tiers.append({"itemPriceTierUuid": uuid_, "itemUuid": item_uuid,
                      "providerItemUuid": provider_item_uuid, "segmentUuid": segment_uuid,
                      "paxType": pax_type, "pricePerUom": price, "currency": "USD", "status": "active"})
    return tiers


def _route_label(item: dict) -> str:
    ext_id = item.get("itemExternalId") or ""
    parts = ext_id.split("-")
    if len(parts) >= 3:
        return f"{parts[1]}->{parts[2]}"
    return item.get("itemName") or item.get("itemUuid") or "Component"


def seed_bundle(engine: RFQEngine, legs: list[dict], idx: int) -> dict | None:
    labels = [_route_label(leg["item"]) for leg in legs]
    code = f"{CONFIG['batch_id_prefix']}-PKG-{idx:03d}"
    name = f"{CONFIG['item_type'].title()} Package " + " + ".join(labels[:3])
    data = run_graphql(engine, BUNDLE_MUTATION, {
        "code": code, "name": name[:180], "type": CONFIG["bundle_type"],
        "desc": f"Multi-component {CONFIG['item_type']} package template.",
        "extra": {"source": "prepare_products", "domain": DOMAIN, "componentCount": len(legs), "routes": labels},
        "stat": "active", "by": UPDATED_BY,
    })
    if not data:
        return None
    b = data["insertUpdateBundle"]["bundle"]
    return {"bundleUuid": b["bundleUuid"], "bundleCode": b.get("bundleCode") or code,
            "bundleName": b.get("bundleName") or name[:180], "bundleType": CONFIG["bundle_type"],
            "status": "active"}


def seed_bundle_component(engine: RFQEngine, *, bundle_uuid: str, leg: dict, sort_order: int) -> dict | None:
    item = leg["item"]; pi = leg["provider_item"]
    data = run_graphql(engine, BUNDLE_COMPONENT_MUTATION, {
        "bundle": bundle_uuid, "item": item["itemUuid"],
        "provider": pi["providerItemUuid"], "role": CONFIG["component_role"],
        "required": True, "qty": 1.0, "order": float(sort_order),
        "extra": {"route": _route_label(item), "itemExternalId": item.get("itemExternalId")},
        "stat": "active", "by": UPDATED_BY,
    })
    if not data:
        return None
    c = data["insertUpdateBundleComponent"]["bundleComponent"]
    return {"bundleComponentUuid": c["bundleComponentUuid"], "bundleUuid": bundle_uuid,
            "itemUuid": item["itemUuid"], "providerItemUuid": pi["providerItemUuid"],
            "componentRole": CONFIG["component_role"], "sortOrder": float(sort_order), "status": "active"}


def seed_bundles(engine: RFQEngine, output: dict) -> None:
    legs_by_item = {i["itemUuid"]: {"item": i, "provider_item": None} for i in output["items"]}
    for pi in output["provider_items"]:
        iuuid = pi.get("itemUuid")
        if iuuid in legs_by_item and not legs_by_item[iuuid]["provider_item"]:
            legs_by_item[iuuid]["provider_item"] = pi
    available = [l for l in legs_by_item.values() if l.get("item") and l.get("provider_item")]
    if len(available) < 2 or NUM_BUNDLES <= 0:
        return
    for idx in range(1, min(NUM_BUNDLES, len(available)) + 1):
        legs = random.sample(available, min(BUNDLE_SIZE, len(available)))
        bundle = seed_bundle(engine, legs, idx)
        if not bundle:
            continue
        output["bundles"].append(bundle)
        for order, leg in enumerate(legs, start=1):
            comp = seed_bundle_component(engine, bundle_uuid=bundle["bundleUuid"], leg=leg, sort_order=order)
            if comp:
                output["bundle_components"].append(comp)


# --- Orchestrator ----------------------------------------------------------- #

def generate(engine: RFQEngine) -> dict:
    segment_uuid = lookup_segment_uuid(engine)
    output: dict = {
        "domain": DOMAIN, "segmentUuid": segment_uuid,
        "cancellation_policies": [], "items": [], "provider_items": [],
        "provider_item_batches": [], "item_price_tiers": [],
        "bundles": [], "bundle_components": [],
    }
    logger.info("--- Domain=%s: %d items, %d batches each → %s ---", DOMAIN, NUM_ROUTES, BATCHES_PER_ROUTE, OUTPUT_FILE)
    policy_by_variant: dict[str, str] = {}
    for route_idx in range(NUM_ROUTES):
        route = pick_route(); variant = pick_variant(); supplier = pick_supplier()
        (orig_code, _), (dest_code, _) = route
        logger.info("[%d/%d] %s %s %s->%s", route_idx + 1, NUM_ROUTES, supplier[1], variant["name"], orig_code, dest_code)
        if variant["name"] not in policy_by_variant:
            policy = seed_cancellation_policy(engine, variant["name"])
            if not policy:
                continue
            policy_by_variant[variant["name"]] = policy["policyUuid"]
            output["cancellation_policies"].append(policy)
        pol_uuid = policy_by_variant[variant["name"]]
        item = seed_item(engine, route, variant)
        if not item:
            continue
        output["items"].append(item)
        pi = seed_provider_item(engine, item["itemUuid"], supplier, variant, route)
        if not pi:
            continue
        output["provider_items"].append(pi)
        for _ in range(BATCHES_PER_ROUTE):
            batch = seed_batch(engine, item["itemUuid"], pi["providerItemUuid"], supplier, route, variant, pol_uuid, random.randint(14, 120))
            if batch:
                output["provider_item_batches"].append(batch)
        tiers = seed_price_tiers(engine, item["itemUuid"], pi["providerItemUuid"], segment_uuid, variant)
        output["item_price_tiers"].extend(tiers)
    seed_bundles(engine, output)
    return output


def write_output(output: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    logger.info(
        "Wrote: %d items, %d provider_items, %d batches, %d tiers, %d policies, %d bundles, %d components -> %s",
        len(output["items"]), len(output["provider_items"]), len(output["provider_item_batches"]),
        len(output["item_price_tiers"]), len(output["cancellation_policies"]),
        len(output["bundles"]), len(output["bundle_components"]), OUTPUT_FILE,
    )


if __name__ == "__main__":
    engine = create_engine()
    result = generate(engine)
    write_output(result)
    logger.info("--- Done ---")