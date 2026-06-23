# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for ProviderItemBatch entity.

Mirrors the DynamoDB ProviderItemBatchModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers (provider_item_uuid, item_uuid, cancellation_policy_uuid)
- String for non-UUID keys (batch_no)
- NUMERIC for money and quantities (NumberAttribute)
- Boolean for BooleanAttribute (slow_move_item, in_stock)
- TIMESTAMP(timezone=True) for timestamps
- Explicit indexes for all LSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Boolean,
    Column,
    Index,
    Numeric,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, prefixed_index, prefixed_table


class ProviderItemBatchModel(Base):
    """SQLAlchemy model for the ProviderItemBatch entity (table: provider_item_batches)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("provider_item_batches")
    # Primary key: composite (provider_item_uuid, batch_no)
    # NOTE: provider_item_uuid is a UUID but is the hash key, not auto-generated.
    provider_item_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    batch_no = Column(String(128), nullable=False, primary_key=True)

    # Batch attributes
    item_uuid = Column(UUID(as_uuid=True))
    partition_key = Column(String(128))
    expired_at = Column(TIMESTAMP(timezone=True))
    produced_at = Column(TIMESTAMP(timezone=True))
    service_start_at = Column(TIMESTAMP(timezone=True))
    service_end_at = Column(TIMESTAMP(timezone=True))
    cost_per_uom = Column(Numeric(18, 6))
    freight_cost_per_uom = Column(Numeric(18, 6))
    additional_cost_per_uom = Column(Numeric(18, 6))
    total_cost_per_uom = Column(Numeric(18, 6))
    guardrail_margin_per_uom = Column(
        Numeric(18, 6), nullable=False, server_default=text("0")
    )
    guardrail_price_per_uom = Column(Numeric(18, 6))
    slow_move_item = Column(
        Boolean, nullable=False, server_default=text("false")
    )
    in_stock = Column(
        Boolean, nullable=False, server_default=text("true")
    )
    availability_qty = Column(Numeric(18, 6))
    currency = Column(String(16))
    cancellation_policy_uuid = Column(UUID(as_uuid=True))

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
        # LSI equivalents: item_uuid-index, updated_at-index
        # NOTE: The DynamoDB LSIs are keyed by provider_item_uuid (hash) with
        # item_uuid / updated_at as range. In PG we create composite indexes
        # that include provider_item_uuid for efficient lookup.
        Index(
            "idx_provider_item_batches_piu_item_uuid",
            "provider_item_uuid",
            "item_uuid",
        ),
        Index(
            "idx_provider_item_batches_piu_updated_at",
            "provider_item_uuid",
            "updated_at",
        ),
        # Additional index for partition_key filtering
        Index(
            "idx_provider_item_batches_partition_key",
            "partition_key",
        ),
    )


__all__ = ["ProviderItemBatchModel"]