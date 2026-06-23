# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Request entity.

Mirrors the DynamoDB RequestModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- JSONB for MapAttribute/ListAttribute fields (billing_address, shipping_address, items)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute
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
from sqlalchemy.dialects.postgresql import UUID, JSONB

from .base import Base, prefixed_index, prefixed_table


class RequestModel(Base):
    """SQLAlchemy model for the Request entity (table: requests)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("requests")
    # Primary key: composite (partition_key, request_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    request_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Request attributes
    email = Column(String(255), nullable=False)
    request_title = Column(String(255), nullable=False)
    request_description = Column(Text, nullable=True)
    billing_address = Column(JSONB, nullable=True)
    shipping_address = Column(JSONB, nullable=True)
    items = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    bundle_uuid = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String(32), nullable=False, default="initial")
    expired_at = Column(TIMESTAMP(timezone=True), nullable=True)

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
        # LSI equivalents: email-index, updated_at-index
        Index(
            "idx_requests_partition_email",
            "partition_key",
            "email",
        ),
        Index(
            "idx_requests_partition_updated_at",
            "partition_key",
            "updated_at",
        ),
    )


__all__ = ["RequestModel"]