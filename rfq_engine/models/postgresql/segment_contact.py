# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for SegmentContact entity.

Mirrors the DynamoDB SegmentContactModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers (segment_uuid, contact_uuid)
- String for non-UUID keys (email)
- TIMESTAMP(timezone=True) for timestamps
- Explicit indexes for all LSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class SegmentContactModel(Base):
    """SQLAlchemy model for the SegmentContact entity (table: segment_contacts)."""

    __tablename__ = "segment_contacts"

    # Primary key: composite (partition_key, email)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    email = Column(String(255), nullable=False, primary_key=True)

    # Segment contact attributes
    segment_uuid = Column(UUID(as_uuid=True))
    contact_uuid = Column(UUID(as_uuid=True))
    consumer_corp_external_id = Column(
        String(255), nullable=False, server_default=text("'XXXXXXXXXXXXXXXXXXXX'")
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
        # LSI equivalents: consumer_corp_external_id-index,
        # segment_uuid-index, updated_at-index
        Index(
            "idx_segment_contacts_partition_consumer_corp",
            "partition_key",
            "consumer_corp_external_id",
        ),
        Index(
            "idx_segment_contacts_partition_segment_uuid",
            "partition_key",
            "segment_uuid",
        ),
        Index(
            "idx_segment_contacts_partition_updated_at",
            "partition_key",
            "updated_at",
        ),
    )


__all__ = ["SegmentContactModel"]