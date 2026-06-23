# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for File entity.

Mirrors the DynamoDB FileModel schema with PostgreSQL-appropriate types:
- UUID columns for UUID identifiers (request_uuid)
- String for non-UUID identifiers (file_name)
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
    text,
)
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, prefixed_index, prefixed_table


class FileModel(Base):
    """SQLAlchemy model for the File entity (table: files)."""

    @declared_attr

    def __tablename__(cls) -> str:

        return prefixed_table("files")
    # Primary key: composite (request_uuid, file_name)
    request_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    file_name = Column(String(512), nullable=False, primary_key=True)

    # Attributes
    email = Column(String(255), nullable=False)
    partition_key = Column(String(128), nullable=False)

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
            "idx_files_request_email",
            "request_uuid",
            "email",
        ),
        Index(
            "idx_files_request_updated_at",
            "request_uuid",
            "updated_at",
        ),
        # Support partition_key filtering
        Index(
            "idx_files_partition_key",
            "partition_key",
        ),
    )


__all__ = ["FileModel"]