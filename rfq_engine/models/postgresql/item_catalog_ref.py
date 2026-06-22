# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for ItemCatalogRef entity.

Mirrors the DynamoDB ItemCatalogRefModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- String for non-UUID identifiers (namespace, node_id, namespace_node_key, item_lookup_key)
- JSONB for MapAttribute fields (extra)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute fields
- Explicit indexes for all DynamoDB LSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    String,
    TIMESTAMP,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base


class ItemCatalogRefModel(Base):
    """SQLAlchemy model for the ItemCatalogRef entity (table: item_catalog_refs)."""

    __tablename__ = "item_catalog_refs"

    # Primary key: composite (partition_key, catalog_ref_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    catalog_ref_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # ItemCatalogRef attributes
    namespace = Column(String(128), nullable=False, server_default=text("'DEFAULT'"))
    node_id = Column(String(255), nullable=False)
    namespace_node_key = Column(String(512), nullable=False)
    extra = Column(JSONB)
    item_uuid = Column(UUID(as_uuid=True), nullable=False)
    item_lookup_key = Column(String(255), nullable=False)
    provider_item_uuid = Column(UUID(as_uuid=True))
    status = Column(String(32), nullable=False, server_default=text("'active'"))

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
        # LSI equivalents: namespace_node_index, item_lookup_index, updated_at-index
        Index("idx_item_catalog_refs_partition_namespace_node_key", "partition_key", "namespace_node_key"),
        Index("idx_item_catalog_refs_partition_item_lookup_key", "partition_key", "item_lookup_key"),
        Index("idx_item_catalog_refs_partition_updated_at", "partition_key", "updated_at"),
    )


__all__ = ["ItemCatalogRefModel"]