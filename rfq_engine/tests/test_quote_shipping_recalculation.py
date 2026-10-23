"""Exercise quote shipping updates against a real, disposable ORM database."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pendulum
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles, deregister
from sqlalchemy.orm import scoped_session, sessionmaker

from rfq_engine.handlers.config import Config
from rfq_engine.models.postgresql.quote import QuoteModel
from rfq_engine.models.postgresql.quote_item import QuoteItemModel
from rfq_engine.models.repositories.postgresql.quote_repo import QuotePGRepository


@pytest.fixture
def repository(monkeypatch):
    # SQLite is used only to exercise persistence/aggregation without a live PG
    # dependency. JSONB is not queried in these regression cases.
    @compiles(JSONB, "sqlite")
    def jsonb_as_json(_type, compiler, **kwargs):
        return "JSON"

    engine = create_engine("sqlite://")
    QuoteModel.__table__.create(engine)
    QuoteItemModel.__table__.create(engine)
    sessions = scoped_session(sessionmaker(bind=engine))
    monkeypatch.setattr(Config, "db_session", sessions)
    info = SimpleNamespace(context={"partition_key": "tenant-shipping"})
    try:
        yield QuotePGRepository(), info, sessions
    finally:
        sessions.remove()
        engine.dispose()
        deregister(JSONB)


@pytest.mark.parametrize("shipping", [Decimal("25"), Decimal("0"), Decimal("0.10")])
def test_shipping_update_recomputes_from_discounted_items(repository, shipping):
    repo, info, sessions = repository
    request_id, quote_id = uuid4(), uuid4()
    repo.insert_update(info, request_uuid=request_id, quote_uuid=quote_id,
                       shipping_amount=50, updated_by="test")
    for partition, final in [("tenant-shipping", "99.50"),
                             ("tenant-shipping", "35.25"),
                             ("another-tenant", "1000")]:
        sessions.add(QuoteItemModel(
            request_uuid=request_id, quote_uuid=quote_id, quote_item_uuid=uuid4(),
            provider_item_uuid=uuid4(), item_uuid=uuid4(), partition_key=partition,
            qty=1, price_per_uom=100, subtotal=100, subtotal_discount=0,
            final_subtotal=Decimal(final), updated_by="test",
            created_at=pendulum.now("UTC"), updated_at=pendulum.now("UTC"),
        ))
    sessions.commit()
    # Existing aggregate fields are deliberately stale. Recalculate from items,
    # applying discounts and the tenant filter instead of trusting old totals.
    result = repo.insert_update(info, request_uuid=request_id, quote_uuid=quote_id,
                                shipping_amount=shipping, updated_by="test")
    assert Decimal(str(result["final_total_quote_amount"])) == Decimal("134.75") + shipping
    persisted = repo.get(request_uuid=request_id, quote_uuid=quote_id)
    assert persisted["final_total_quote_amount"] == result["final_total_quote_amount"]


def test_new_quote_with_shipping_and_no_items(repository):
    repo, info, _ = repository
    result = repo.insert_update(info, request_uuid=uuid4(), quote_uuid=uuid4(),
                                shipping_amount=Decimal("25.50"), updated_by="test")
    assert Decimal(str(result["final_total_quote_amount"])) == Decimal("25.50")
