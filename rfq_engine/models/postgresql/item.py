# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Item entity.

Mirrors the DynamoDB ItemModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- TIMESTAMP(timezone=True) for timestamps
- Explicit indexes for all query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    String,
    Text,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class ItemModel(Base):
    """SQLAlchemy model for the Item entity (table: items)."""

    __tablename__ = "items"

    # Primary key: composite (partition_key, item_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    item_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Item attributes
    item_type = Column(String(64), nullable=False)
    item_name = Column(String(255), nullable=False)
    item_description = Column(Text)
    pricing_mode = Column(String(64))
    uom = Column(String(64), nullable=False)
    item_external_id = Column(String(255))

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
        # LSI equivalents: item_type-index, updated_at-index
        Index("idx_items_partition_item_type", "partition_key", "item_type"),
        Index("idx_items_partition_updated_at", "partition_key", "updated_at"),
        # GSI equivalent for item_external_id lookup
        Index("idx_items_partition_external_id", "partition_key", "item_external_id"),
    )


__all__ = ["ItemModel"]