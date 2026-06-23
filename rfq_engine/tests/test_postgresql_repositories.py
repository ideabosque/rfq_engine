# -*- coding: utf-8 -*-
"""PostgreSQL repository tests via the GraphQL engine.

These tests exercise item CRUD through ``RFQEngine.ai_rfq_graphql``
mutations and queries against a real PostgreSQL instance — not via
direct ``ItemPGRepository`` method calls. They are skipped automatically
when no PostgreSQL connection is available.

Connection selection (first match wins):
    1. ``DATABASE_URL`` env var
    2. ``PG_HOST`` / ``PG_PORT`` / ``PG_USER`` / ``PG_PASSWORD`` / ``PG_DB``
       env vars

The fixture ensures all 18 tables exist (idempotent ``create_all``),
wires ``Config`` to PostgreSQL, initializes an ``RFQEngine`` instance, and
cleans up test rows on teardown. Tests are marked ``integration``.
"""
from __future__ import print_function

__author__ = "bibow"

import os
import uuid
from typing import Any, Dict, Optional

import pytest

pytestmark = pytest.mark.integration


def _resolve_database_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("PG_HOST")
    if not host:
        return None
    from urllib.parse import quote_plus

    user = os.getenv("PG_USER", "rfq")
    password = quote_plus(os.getenv("PG_PASSWORD", ""))
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DB", os.getenv("PG_SCHEMA", "rfq_engine"))
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def _can_connect(url: str) -> bool:
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_DATABASE_URL = _resolve_database_url()
_PG_AVAILABLE = bool(_DATABASE_URL) and _can_connect(_DATABASE_URL)


@pytest.fixture(scope="module")
def engine():
    """Provide an ``RFQEngine`` instance bound to PostgreSQL.

    Ensures all 18 tables exist, wires ``Config``, initializes the engine,
    and cleans up test rows on teardown. Skips when PostgreSQL is not
    reachable.
    """
    if not _PG_AVAILABLE:
        pytest.skip("PostgreSQL not available — set DATABASE_URL or PG_HOST/PG_*")

    import logging

    from sqlalchemy import create_engine, delete
    from sqlalchemy.orm import scoped_session, sessionmaker

    from rfq_engine.handlers.config import Config
    from rfq_engine.models.postgresql.base import Base
    import rfq_engine.models.postgresql.item  # noqa: F401
    import rfq_engine.models.postgresql.provider_item  # noqa: F401
    import rfq_engine.models.postgresql.provider_item_batch  # noqa: F401
    import rfq_engine.models.postgresql.segment  # noqa: F401
    import rfq_engine.models.postgresql.segment_contact  # noqa: F401
    import rfq_engine.models.postgresql.fx_rate  # noqa: F401
    import rfq_engine.models.postgresql.cancellation_policy  # noqa: F401
    import rfq_engine.models.postgresql.bundle  # noqa: F401
    import rfq_engine.models.postgresql.bundle_component  # noqa: F401
    import rfq_engine.models.postgresql.item_catalog_ref  # noqa: F401
    import rfq_engine.models.postgresql.item_price_tier  # noqa: F401
    import rfq_engine.models.postgresql.discount_prompt  # noqa: F401
    import rfq_engine.models.postgresql.request  # noqa: F401
    import rfq_engine.models.postgresql.quote  # noqa: F401
    import rfq_engine.models.postgresql.quote_item  # noqa: F401
    import rfq_engine.models.postgresql.installment  # noqa: F401
    import rfq_engine.models.postgresql.file  # noqa: F401
    import rfq_engine.models.postgresql.availability_hold  # noqa: F401
    from rfq_engine import RFQEngine

    sa_engine = create_engine(_DATABASE_URL, pool_pre_ping=True, echo=False)
    Base.metadata.create_all(sa_engine, checkfirst=True)
    session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=sa_engine)
    )

    Config.DB_BACKEND = "postgresql"
    Config.db_session = session
    Config._initialized = True

    setting = {
        "db_backend": "postgresql",
        "db_host": os.getenv("PG_HOST", "localhost"),
        "db_port": int(os.getenv("PG_PORT", "5432")),
        "db_user": os.getenv("PG_USER", "silvaengine"),
        "db_password": os.getenv("PG_PASSWORD", "silvaengine"),
        "db_schema": os.getenv("PG_DB", "silvaengine"),
        "functs_on_local": {
            "ai_rfq_graphql": {
                "module_name": "rfq_engine",
                "class_name": "RFQEngine",
            }
        },
        "endpoint_id": "test",
        "part_id": "pytest",
        "execute_mode": "local_for_all",
        "initialize_tables": False,
        "cache_enabled": False,
        "pg_table_prefix": os.getenv("PG_TABLE_PREFIX", "rfq_"),
    }

    logger = logging.getLogger("test_pg_graphql")
    rfq_engine = RFQEngine(logger, **setting)
    setattr(rfq_engine, "__is_real__", True)

    yield rfq_engine

    from rfq_engine.models.postgresql.item import ItemModel

    session.execute(delete(ItemModel).where(ItemModel.partition_key == "test#pytest"))
    session.commit()
    session.remove()
    sa_engine.dispose()


def _gql(engine, query: str, variables: dict) -> dict:
    """Execute a GraphQL operation and return the parsed response."""
    from silvaengine_utility.serializer import Serializer

    resp = engine.ai_rfq_graphql(
        query=query,
        variables=variables,
        endpoint_id="test",
        part_id="pytest",
    )
    parsed = (
        Serializer.json_loads(resp) if isinstance(resp, (str, bytes)) else resp
    )
    if isinstance(parsed, dict) and isinstance(parsed.get("body"), str):
        parsed = Serializer.json_loads(parsed["body"])
    return parsed


CREATE_ITEM_MUTATION = """
mutation CreateItem($type:String,$name:String,$uom:String,$by:String!){
    insertUpdateItem(itemType:$type,itemName:$name,uom:$uom,updatedBy:$by){
        item{itemUuid itemName itemType}
    }
}
"""

GET_ITEM_QUERY = """
query GetItem($uuid:String!){
    item(itemUuid:$uuid){itemUuid itemName itemType}
}
"""

UPDATE_ITEM_MUTATION = """
mutation UpdateItem($uuid:String!,$name:String,$by:String!){
    insertUpdateItem(itemUuid:$uuid,itemName:$name,updatedBy:$by){
        item{itemName}
    }
}
"""

ITEM_LIST_QUERY = """
query ItemList($type:String,$limit:Int){
    itemList(itemType:$type,limit:$limit){itemList{itemUuid itemName}total}
}
"""

DELETE_ITEM_MUTATION = """
mutation DeleteItem($uuid:String!){
    deleteItem(itemUuid:$uuid){ok}
}
"""


def test_graphql_item_create_and_query(engine):
    """Create an item via GraphQL mutation and query it back via GraphQL."""
    item_uuid = str(uuid.uuid4())

    resp = _gql(engine, CREATE_ITEM_MUTATION, {
        "type": "test_product", "name": "GraphQL Test Item", "uom": "each", "by": "tester",
    })
    data = resp.get("data", {}).get("insertUpdateItem", {}).get("item", {})
    assert data.get("itemUuid") is not None, f"Create failed: {resp}"
    assert data.get("itemName") == "GraphQL Test Item"
    assert data.get("itemType") == "test_product"

    created_uuid = data["itemUuid"]
    resp = _gql(engine, GET_ITEM_QUERY, {"uuid": created_uuid})
    item = resp.get("data", {}).get("item", {})
    assert item.get("itemName") == "GraphQL Test Item", f"Query failed: {resp}"
    assert item.get("itemType") == "test_product"


def test_graphql_item_update_and_delete(engine):
    """Update an item via GraphQL mutation, then delete it and verify null."""
    resp = _gql(engine, CREATE_ITEM_MUTATION, {
        "type": "test_product", "name": "Item To Update", "uom": "each", "by": "tester",
    })
    item_uuid = resp["data"]["insertUpdateItem"]["item"]["itemUuid"]

    resp = _gql(engine, UPDATE_ITEM_MUTATION, {
        "uuid": item_uuid, "name": "Updated Name", "by": "tester2",
    })
    assert resp["data"]["insertUpdateItem"]["item"]["itemName"] == "Updated Name"

    resp = _gql(engine, GET_ITEM_QUERY, {"uuid": item_uuid})
    assert resp["data"]["item"]["itemName"] == "Updated Name"

    resp = _gql(engine, DELETE_ITEM_MUTATION, {"uuid": item_uuid})
    assert resp["data"]["deleteItem"]["ok"] is True

    resp = _gql(engine, GET_ITEM_QUERY, {"uuid": item_uuid})
    assert resp["data"]["item"] is None


def test_graphql_item_list_filter_and_paginate(engine):
    """Create multiple items via GraphQL, then list with filter via GraphQL."""
    for i in range(5):
        _gql(engine, CREATE_ITEM_MUTATION, {
            "type": "list_test_a" if i < 3 else "list_test_b",
            "name": f"List Test {i}", "uom": "each", "by": "tester",
        })

    resp = _gql(engine, ITEM_LIST_QUERY, {"type": "list_test_a", "limit": 10})
    total = resp["data"]["itemList"]["total"]
    assert total >= 3, f"Expected >= 3 list_test_a items, got {total}"

    resp = _gql(engine, ITEM_LIST_QUERY, {"type": "list_test_b", "limit": 10})
    total_b = resp["data"]["itemList"]["total"]
    assert total_b >= 2, f"Expected >= 2 list_test_b items, got {total_b}"