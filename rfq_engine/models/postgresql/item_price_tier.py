# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for ItemPriceTier entity.

Mirrors the DynamoDB ItemPriceTierModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- NUMERIC for NumberAttribute fields (money, quantities)
- JSONB for MapAttribute fields (base_occupancy, extra_pax_surcharges)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute
- Explicit indexes for all LSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    String,
    TIMESTAMP,
    Numeric,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID, JSONB

from .base import Base, prefixed_index, prefixed_table


class ItemPriceTierModel(Base):
    """SQLAlchemy model for the ItemPriceTier entity (table: item_price_tiers)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("item_price_tiers")
    # Primary key: composite (item_uuid, item_price_tier_uuid)
    item_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    item_price_tier_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Attributes
    provider_item_uuid = Column(UUID(as_uuid=True))
    segment_uuid = Column(UUID(as_uuid=True))
    partition_key = Column(String(128), nullable=False)
    quantity_greater_then = Column(Numeric, nullable=False)
    quantity_less_then = Column(Numeric, nullable=True)
    pax_type = Column(String(64), nullable=True)
    margin_per_uom = Column(Numeric, nullable=True)
    price_per_uom = Column(Numeric, nullable=True)
    currency = Column(String(8), nullable=True)
    # G2 occupancy mode: pax_type -> count of guests included in the base rate
    base_occupancy = Column(JSONB, nullable=True)
    # G2 occupancy mode: pax_type -> surcharge per extra guest beyond base
    extra_pax_surcharges = Column(JSONB, nullable=True)
    status = Column(String(32), nullable=False, default="in_review")

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
        # LSI equivalents: provider_item_uuid-index, segment_uuid-index, updated_at-index
        Index(
            "idx_item_price_tiers_item_provider_item_uuid",
            "item_uuid",
            "provider_item_uuid",
        ),
        Index(
            "idx_item_price_tiers_item_segment_uuid",
            "item_uuid",
            "segment_uuid",
        ),
        Index(
            "idx_item_price_tiers_item_updated_at",
            "item_uuid",
            "updated_at",
        ),
        # Support partition_key filtering
        Index(
            "idx_item_price_tiers_partition_key",
            "partition_key",
        ),
    )


__all__ = ["ItemPriceTierModel"]