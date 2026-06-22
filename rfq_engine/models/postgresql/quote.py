# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Quote entity.

Mirrors the DynamoDB QuoteModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- NUMERIC for NumberAttribute fields (amounts, rates, rounds)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute
- Explicit indexes for all LSI/GSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    String,
    Text,
    TIMESTAMP,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class QuoteModel(Base):
    """SQLAlchemy model for the Quote entity (table: quotes)."""

    __tablename__ = "quotes"

    # Primary key: composite (request_uuid, quote_uuid)
    request_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    quote_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Attributes
    provider_corp_external_id = Column(String(255), nullable=False, default="XXXXXXXXXXXXXXXXXXXX")
    sales_rep_email = Column(String(255), nullable=True)
    partition_key = Column(String(128), nullable=False)
    shipping_method = Column(String(64), nullable=True)
    shipping_amount = Column(Numeric, nullable=False, default=0)
    total_quote_amount = Column(Numeric, nullable=False, default=0)
    total_quote_discount = Column(Numeric, nullable=False, default=0)
    final_total_quote_amount = Column(Numeric, nullable=False, default=0)
    currency = Column(String(8), nullable=True)
    display_currency = Column(String(8), nullable=True)
    fx_rate = Column(Numeric, nullable=True)
    fx_rate_locked_at = Column(TIMESTAMP(timezone=True), nullable=True)
    rounds = Column(Numeric, nullable=False, default=0)
    notes = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="initial")

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
            "idx_quotes_request_provider_corp_external_id",
            "request_uuid",
            "provider_corp_external_id",
        ),
        Index(
            "idx_quotes_request_updated_at",
            "request_uuid",
            "updated_at",
        ),
        # GSI equivalent: provider_corp_external_id-quote_uuid-index
        Index(
            "idx_quotes_provider_corp_external_id_quote_uuid",
            "provider_corp_external_id",
            "quote_uuid",
        ),
        # Support partition_key filtering
        Index(
            "idx_quotes_partition_key",
            "partition_key",
        ),
    )


__all__ = ["QuoteModel"]