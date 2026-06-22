# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for AvailabilityHold entity.

Mirrors the DynamoDB AvailabilityHoldModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers (hold_token, provider_item_uuid, quote_uuid, quote_item_uuid)
- String for non-UUID identifiers (batch_no)
- NUMERIC for NumberAttribute fields (qty)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute
- Explicit indexes for query/filter paths

AvailabilityHold uses backend-specific atomic transaction semantics
(SELECT...FOR UPDATE pattern for PostgreSQL) and is not managed via
standard CRUD repositories. See AvailabilityHoldPGRepository.
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
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class AvailabilityHoldModel(Base):
    """SQLAlchemy model for the AvailabilityHold entity (table: availability_holds)."""

    __tablename__ = "availability_holds"

    # Status constants (mirror DynamoDB model)
    HELD = "held"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    EXPIRED = "expired"

    # Primary key: composite (partition_key, hold_token)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    hold_token = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Attributes
    provider_item_uuid = Column(UUID(as_uuid=True), nullable=False)
    batch_no = Column(String(128), nullable=False)
    quote_uuid = Column(UUID(as_uuid=True), nullable=True)
    quote_item_uuid = Column(UUID(as_uuid=True), nullable=True)
    qty = Column(Numeric, nullable=False)
    service_start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    service_end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default=HELD)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        server_onupdate=text("NOW()"),
    )
    updated_by = Column(String(64), nullable=False)

    __table_args__ = (
        # Index for provider_item_uuid lookups (hold queries by provider item)
        Index(
            "idx_availability_holds_provider_item_uuid",
            "provider_item_uuid",
        ),
        # Index for quote_uuid lookups (finding holds for a quote)
        Index(
            "idx_availability_holds_quote_uuid",
            "quote_uuid",
        ),
        # Index for status filtering (find active/expired holds)
        Index(
            "idx_availability_holds_status",
            "status",
        ),
        # Index for expiry scanning (find expired holds for cleanup)
        Index(
            "idx_availability_holds_expires_at",
            "expires_at",
        ),
    )


__all__ = ["AvailabilityHoldModel"]