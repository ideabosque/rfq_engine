# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for CancellationPolicy entity.

Mirrors the DynamoDB CancellationPolicyModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- JSONB for MapAttribute fields (tiers)
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


class CancellationPolicyModel(Base):
    """SQLAlchemy model for the CancellationPolicy entity (table: cancellation_policies)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("cancellation_policies")
    # Primary key: composite (partition_key, policy_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    policy_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # CancellationPolicy attributes
    provider_item_uuid = Column(UUID(as_uuid=True))
    label = Column(String(255))
    description = Column(Text)
    tiers = Column(JSONB)
    notes_template_uuid = Column(UUID(as_uuid=True))
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
        # LSI equivalents: provider_item_uuid-index, updated_at-index
        Index(prefixed_index("idx_cancellation_policies_partition_provider_item_uuid"), "partition_key", "provider_item_uuid"),
        Index(prefixed_index("idx_cancellation_policies_partition_updated_at"), "partition_key", "updated_at"),
    )


__all__ = ["CancellationPolicyModel"]