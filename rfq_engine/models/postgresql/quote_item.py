# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for QuoteItem entity.

Mirrors the DynamoDB QuoteItemModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- String for non-UUID identifiers (batch_no, hold_token)
- NUMERIC for NumberAttribute fields (prices, quantities, subtotals)
- JSONB for MapAttribute fields (request_data, pax_breakdown)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute
- Explicit indexes for all LSI/GSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    String,
    Text,
    TIMESTAMP,
    Numeric,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID, JSONB

from .base import Base, prefixed_index, prefixed_table


class QuoteItemModel(Base):
    """SQLAlchemy model for the QuoteItem entity (table: quote_items)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("quote_items")
    # Primary key: composite (quote_uuid, quote_item_uuid)
    quote_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    quote_item_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Attributes
    provider_item_uuid = Column(UUID(as_uuid=True), nullable=False)
    item_uuid = Column(UUID(as_uuid=True), nullable=False)
    batch_no = Column(String(128), nullable=True)
    request_uuid = Column(UUID(as_uuid=True), nullable=False)
    partition_key = Column(String(128), nullable=False)
    request_data = Column(JSONB, nullable=True)
    price_per_uom = Column(Numeric, nullable=False)
    qty = Column(Numeric, nullable=False)
    pax_breakdown = Column(JSONB, nullable=True)
    bundle_uuid = Column(UUID(as_uuid=True), nullable=True)
    bundle_label = Column(String(255), nullable=True)
    bundle_component_uuid = Column(UUID(as_uuid=True), nullable=True)
    subtotal = Column(Numeric, nullable=False)
    subtotal_discount = Column(Numeric, nullable=True)
    final_subtotal = Column(Numeric, nullable=False)
    currency = Column(String(8), nullable=True)
    subtotal_native = Column(Numeric, nullable=True)
    notes = Column(Text, nullable=True)
    hold_token = Column(String(128), nullable=True)
    hold_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_by = Column(String(64), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        server_onupdate=text("NOW()"),
    )

    __table_args__ = (
        # LSI equivalents: provider_item_uuid-index, item_uuid-index, updated_at-index
        Index(
            "idx_quote_items_quote_provider_item_uuid",
            "quote_uuid",
            "provider_item_uuid",
        ),
        Index(
            "idx_quote_items_quote_item_uuid",
            "quote_uuid",
            "item_uuid",
        ),
        Index(
            "idx_quote_items_quote_updated_at",
            "quote_uuid",
            "updated_at",
        ),
        # GSI equivalent: item_uuid-provider_item_uuid-index
        Index(
            "idx_quote_items_item_uuid_provider_item_uuid",
            "item_uuid",
            "provider_item_uuid",
        ),
        # Support partition_key and request_uuid filtering
        Index(
            "idx_quote_items_partition_key",
            "partition_key",
        ),
        Index(
            "idx_quote_items_request_uuid",
            "request_uuid",
        ),
    )


__all__ = ["QuoteItemModel"]