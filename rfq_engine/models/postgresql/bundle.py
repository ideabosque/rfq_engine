# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Bundle entity.

Mirrors the DynamoDB BundleModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
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
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base, prefixed_index, prefixed_table


class BundleModel(Base):
    """SQLAlchemy model for the Bundle entity (table: bundles)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("bundles")
    # Primary key: composite (partition_key, bundle_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    bundle_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Bundle attributes
    bundle_code = Column(String(128))
    bundle_name = Column(String(255), nullable=False)
    bundle_type = Column(String(64), nullable=False, server_default=text("'package'"))
    description = Column(Text)
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
        # LSI equivalents: bundle_code-index, updated_at-index
        Index(prefixed_index("idx_bundles_partition_bundle_code"), "partition_key", "bundle_code"),
        Index(prefixed_index("idx_bundles_partition_updated_at"), "partition_key", "updated_at"),
    )


__all__ = ["BundleModel"]