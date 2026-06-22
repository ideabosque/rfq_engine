# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Installment entity.

Mirrors the DynamoDB InstallmentModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- NUMERIC for NumberAttribute fields (priority, ratio, amount)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute
- Explicit indexes for all LSI query/filter paths
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


class InstallmentModel(Base):
    """SQLAlchemy model for the Installment entity (table: installments)."""

    __tablename__ = "installments"

    # Primary key: composite (quote_uuid, installment_uuid)
    quote_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    installment_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Attributes
    partition_key = Column(String(128), nullable=False)
    request_uuid = Column(UUID(as_uuid=True), nullable=False)
    priority = Column(Numeric, nullable=False, default=0)
    salesorder_no = Column(String(128), nullable=True)
    payment_method = Column(String(64), nullable=False)
    scheduled_date = Column(TIMESTAMP(timezone=True), nullable=True)
    installment_ratio = Column(Numeric, nullable=False, default=0)
    installment_amount = Column(Numeric, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending")

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
        # LSI equivalent: updated_at-index
        Index(
            "idx_installments_quote_updated_at",
            "quote_uuid",
            "updated_at",
        ),
        # Support partition_key and request_uuid filtering
        Index(
            "idx_installments_partition_key",
            "partition_key",
        ),
        Index(
            "idx_installments_request_uuid",
            "request_uuid",
        ),
    )


__all__ = ["InstallmentModel"]