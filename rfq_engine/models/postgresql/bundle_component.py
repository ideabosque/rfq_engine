# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for BundleComponent entity.

Mirrors the DynamoDB BundleComponentModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- NUMERIC for NumberAttribute fields (default_qty, sort_order)
- Boolean for BooleanAttribute (required)
- JSONB for MapAttribute fields (extra)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute fields
- Explicit indexes for all DynamoDB LSI query/filter paths
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
    Text,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base, prefixed_index, prefixed_table


class BundleComponentModel(Base):
    """SQLAlchemy model for the BundleComponent entity (table: bundle_components)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("bundle_components")
    # Primary key: composite (partition_key, bundle_component_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    bundle_component_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # BundleComponent attributes
    bundle_uuid = Column(UUID(as_uuid=True), nullable=False)
    item_uuid = Column(UUID(as_uuid=True), nullable=False)
    provider_item_uuid = Column(UUID(as_uuid=True))
    component_role = Column(String(64))
    required = Column(Boolean, nullable=False, server_default=text("true"))
    default_qty = Column(Numeric(18, 4))
    sort_order = Column(Numeric(18, 4))
    extra = Column(JSONB)
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
        # LSI equivalents: bundle_uuid-index, updated_at-index
        Index(prefixed_index("idx_bundle_components_partition_bundle_uuid"), "partition_key", "bundle_uuid"),
        Index(prefixed_index("idx_bundle_components_partition_updated_at"), "partition_key", "updated_at"),
    )


__all__ = ["BundleComponentModel"]