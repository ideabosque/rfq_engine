# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Segment entity.

Mirrors the DynamoDB SegmentModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- TIMESTAMP(timezone=True) for timestamps
- Explicit indexes for all LSI query/filter paths
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
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, prefixed_index, prefixed_table


class SegmentModel(Base):
    """SQLAlchemy model for the Segment entity (table: segments)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("segments")
    # Primary key: composite (partition_key, segment_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    segment_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Segment attributes
    provider_corp_external_id = Column(
        String(255), nullable=False, server_default=text("'XXXXXXXXXXXXXXXXXXXX'")
    )
    segment_name = Column(String(255), nullable=False)
    segment_description = Column(Text)

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
        # LSI equivalents: provider_corp_external_id-index, updated_at-index
        Index(
            "idx_segments_partition_provider_corp",
            "partition_key",
            "provider_corp_external_id",
        ),
        Index(
            "idx_segments_partition_updated_at",
            "partition_key",
            "updated_at",
        ),
    )


__all__ = ["SegmentModel"]