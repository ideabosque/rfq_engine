#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Seed ``are-segments`` and ``are-segment_contacts`` with Faker-generated data.

Runs the same GraphQL mutations as production traffic via ``ai_rfq_graphql``
so validation, audit fields, and cache invalidation behave correctly.

Usage::

    python rfq_engine/tests/prepare_test_data/prepare_segments_and_contacts.py

Counts are configurable via environment variables (or edit the constants
below):

    SEED_NUM_SEGMENTS=5
    SEED_NUM_CONTACTS_PER_SEGMENT=8

Writes the generated UUIDs to ``segments_and_contacts.json`` in this
directory for inspection or downstream chaining.
"""
from __future__ import annotations

__author__ = "bibow"

import json
import logging
import os
import random
import sys

from dotenv import load_dotenv

# Load .env from the tests directory (one level up) before extending sys.path.
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
    sys.exit(
        "The 'faker' package is not installed. Install it with: pip install faker"
    )


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("prepare_segments_and_contacts")

fake = Faker()

UPDATED_BY = "prepare_segments_and_contacts"

OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "segments_and_contacts.json"
)

NUM_SEGMENTS = int(os.getenv("SEED_NUM_SEGMENTS", "3"))
NUM_CONTACTS_PER_SEGMENT = int(os.getenv("SEED_NUM_CONTACTS_PER_SEGMENT", "5"))

from _backend_setting import build_setting  # noqa: E402

SETTING = build_setting()


SEGMENT_MUTATION = """
mutation InsertUpdateSegment(
    $name: String, $desc: String, $extId: String, $by: String!
) {
    insertUpdateSegment(
        segmentName: $name,
        segmentDescription: $desc,
        providerCorpExternalId: $extId,
        updatedBy: $by
    ) {
        segment { segmentUuid }
    }
}
"""

SEGMENT_CONTACT_MUTATION = """
mutation InsertUpdateSegmentContact(
    $sid: String!, $email: String!, $cid: String, $by: String!
) {
    insertUpdateSegmentContact(
        segmentUuid: $sid,
        email: $email,
        consumerCorpExternalId: $cid,
        updatedBy: $by
    ) {
        segmentContact { contactUuid }
    }
}
"""


def create_engine() -> RFQEngine:
    try:
        engine = RFQEngine(logger, **SETTING)
        setattr(engine, "__is_real__", True)
        return engine
    except Exception:
        logger.exception("Failed to initialize RFQEngine")
        raise


def run_mutation(engine: RFQEngine, query: str, variables: dict) -> dict | None:
    try:
        response = engine.ai_rfq_graphql(
            query=query,
            variables=variables,
            endpoint_id=SETTING["endpoint_id"],
            part_id=SETTING["part_id"],
        )
    except Exception:
        logger.exception("GraphQL execution failed")
        return None

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

    if not isinstance(parsed, dict):
        logger.error("Unexpected response: %s", parsed)
        return None
    if parsed.get("errors"):
        logger.error("GraphQL error: %s", Serializer.json_dumps(parsed["errors"]))
        return None
    return parsed.get("data", parsed)


def seed_segment(engine: RFQEngine) -> dict | None:
    name = f"{fake.company()} Tier"
    description = fake.catch_phrase()
    external_id = f"PROV-{random.randint(1000, 9999)}"

    logger.info("Creating segment: %s", name)
    data = run_mutation(
        engine,
        SEGMENT_MUTATION,
        {"name": name, "desc": description, "extId": external_id, "by": UPDATED_BY},
    )
    if not data:
        return None
    segment_uuid = data["insertUpdateSegment"]["segment"]["segmentUuid"]
    logger.info("  -> segmentUuid=%s", segment_uuid)
    return {
        "segmentUuid": segment_uuid,
        "segmentName": name,
        "segmentDescription": description,
        "providerCorpExternalId": external_id,
    }


def seed_contact(engine: RFQEngine, segment_uuid: str) -> dict | None:
    email = fake.unique.email()
    consumer_id = f"CUST-{random.randint(1000, 9999)}"

    logger.info("  Creating contact: %s", email)
    data = run_mutation(
        engine,
        SEGMENT_CONTACT_MUTATION,
        {"sid": segment_uuid, "email": email, "cid": consumer_id, "by": UPDATED_BY},
    )
    if not data:
        return None
    contact_uuid = data["insertUpdateSegmentContact"]["segmentContact"]["contactUuid"]
    return {
        "segmentUuid": segment_uuid,
        "email": email,
        "contactUuid": contact_uuid,
        "consumerCorpExternalId": consumer_id,
    }


def generate_and_load(engine: RFQEngine) -> dict:
    if not SETTING.get("endpoint_id") or not SETTING.get("part_id"):
        raise RuntimeError(
            "endpoint_id and part_id must be set in tests/.env before running"
        )

    output: dict = {"segments": [], "segment_contacts": []}

    logger.info(
        "--- Seeding %d segments, %d contacts each ---",
        NUM_SEGMENTS,
        NUM_CONTACTS_PER_SEGMENT,
    )

    for _ in range(NUM_SEGMENTS):
        segment = seed_segment(engine)
        if not segment:
            continue
        output["segments"].append(segment)
        for _ in range(NUM_CONTACTS_PER_SEGMENT):
            contact = seed_contact(engine, segment["segmentUuid"])
            if contact:
                output["segment_contacts"].append(contact)

    return output


def write_output(output: dict) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    logger.info(
        "Wrote %d segments and %d contacts to %s",
        len(output["segments"]),
        len(output["segment_contacts"]),
        OUTPUT_FILE,
    )


if __name__ == "__main__":
    engine = create_engine()
    result = generate_and_load(engine)
    write_output(result)
    logger.info("--- Done ---")
