# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for ProviderItem entity.

Mirrors the DynamoDB ProviderItemModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- NUMERIC for money (NumberAttribute -> base_price_per_uom)
- JSONB for MapAttribute (item_spec)
- TIMESTAMP(timezone=True) for timestamps
- Explicit indexes for all LSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    Numeric,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base, prefixed_index, prefixed_table


class ProviderItemModel(Base):
    """SQLAlchemy model for the ProviderItem entity (table: provider_items)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("provider_items")
    # Primary key: composite (partition_key, provider_item_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    provider_item_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Provider item attributes
    item_uuid = Column(UUID(as_uuid=True))
    provider_corp_external_id = Column(
        String(255), nullable=False, server_default=text("'XXXXXXXXXXXXXXXXXXXX'")
    )
    provider_item_external_id = Column(String(255))
    base_price_per_uom = Column(Numeric(18, 6))
    item_spec = Column(JSONB)
    availability_mode = Column(
        String(64), nullable=False, server_default=text("'none'")
    )

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
        # LSI equivalents: item_uuid-index, provider_corp_external_id-index,
        # provider_item_external_id-index, updated_at-index
        Index(
            "idx_provider_items_partition_item_uuid",
            "partition_key",
            "item_uuid",
        ),
        Index(
            "idx_provider_items_partition_provider_corp",
            "partition_key",
            "provider_corp_external_id",
        ),
        Index(
            "idx_provider_items_partition_external_id",
            "partition_key",
            "provider_item_external_id",
        ),
        Index(
            "idx_provider_items_partition_updated_at",
            "partition_key",
            "updated_at",
        ),
    )


__all__ = ["ProviderItemModel"]