# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for FxRate entity.

Mirrors the DynamoDB FxRateModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- NUMERIC for NumberAttribute fields (rate)
- TIMESTAMP(timezone=True) for UTCDateTimeAttribute fields
- Explicit indexes for all DynamoDB LSI query/filter paths
"""
from __future__ import print_function

__author__ = "bibow"

from sqlalchemy import (
    Column,
    Index,
    Numeric,
    String,
    TIMESTAMP,
    Text,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, prefixed_index, prefixed_table


class FxRateModel(Base):
    """SQLAlchemy model for the FxRate entity (table: fx_rates)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("fx_rates")
    # Primary key: composite (partition_key, fx_rate_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    fx_rate_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # FxRate attributes
    source_currency = Column(String(8), nullable=False)
    target_currency = Column(String(8), nullable=False)
    rate = Column(Numeric(18, 8), nullable=False)
    currency_pair_date = Column(String(32), nullable=False)
    rate_date = Column(TIMESTAMP(timezone=True))
    provider = Column(String(128))
    notes = Column(Text)
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
        # LSI equivalents: currency_pair_date-index, updated_at-index
        Index(prefixed_index("idx_fx_rates_partition_currency_pair_date"), "partition_key", "currency_pair_date"),
        Index(prefixed_index("idx_fx_rates_partition_updated_at"), "partition_key", "updated_at"),
    )


__all__ = ["FxRateModel"]