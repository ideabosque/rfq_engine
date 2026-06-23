# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for DiscountPrompt entity.

Mirrors the DynamoDB DiscountPromptModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers
- JSONB for ListAttribute/MapAttribute fields (tags, conditions, discount_rules)
- NUMERIC for NumberAttribute fields (priority)
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
    Numeric,
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID, JSONB

from .base import Base, prefixed_index, prefixed_table


class DiscountPromptModel(Base):
    """SQLAlchemy model for the DiscountPrompt entity (table: discount_prompts)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("discount_prompts")
    # Primary key: composite (partition_key, discount_prompt_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    discount_prompt_uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )

    # Attributes
    scope = Column(String(64), nullable=False)
    tags = Column(JSONB, nullable=True)
    discount_prompt = Column(Text, nullable=False)
    conditions = Column(JSONB, nullable=True)
    discount_rules = Column(JSONB, nullable=True)
    priority = Column(Numeric, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="in_review")

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
        # LSI equivalents: scope-index, updated_at-index
        Index(
            "idx_discount_prompts_partition_scope",
            "partition_key",
            "scope",
        ),
        Index(
            "idx_discount_prompts_partition_updated_at",
            "partition_key",
            "updated_at",
        ),
    )


__all__ = ["DiscountPromptModel"]