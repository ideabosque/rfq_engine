# -*- coding: utf-8 -*-
"""PostgreSQL repository for SegmentContact entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL SegmentContactModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.segment_contact import (
    SegmentContactListType,
    SegmentContactType,
)
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.segment_contact import SegmentContactModel


class SegmentContactPGRepository(EntityRepository):
    """PostgreSQL repository for SegmentContact entity."""

    @property
    def entity_type(self) -> str:
        return "segment_contact"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        email = keys.get("email")
        if not partition_key or not email:
            return None
        session = Config.db_session
        row = (
            session.query(SegmentContactModel)
            .filter(
                SegmentContactModel.partition_key == partition_key,
                SegmentContactModel.email == email,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        email = keys.get("email")
        if not partition_key or not email:
            return 0
        session = Config.db_session
        return (
            session.query(SegmentContactModel)
            .filter(
                SegmentContactModel.partition_key == partition_key,
                SegmentContactModel.email == email,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated segment_contact list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        segment_uuid = filters.get("segment_uuid")
        contact_uuid = filters.get("contact_uuid")
        consumer_corp_external_id = filters.get("consumer_corp_external_id")
        email = filters.get("email")

        query = session.query(SegmentContactModel)
        if partition_key:
            query = query.filter(
                SegmentContactModel.partition_key == partition_key
            )
        if segment_uuid:
            query = query.filter(
                SegmentContactModel.segment_uuid == segment_uuid
            )
        if contact_uuid:
            query = query.filter(
                SegmentContactModel.contact_uuid == contact_uuid
            )
        if consumer_corp_external_id:
            query = query.filter(
                SegmentContactModel.consumer_corp_external_id
                == consumer_corp_external_id
            )
        if email:
            query = query.filter(SegmentContactModel.email == email)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(SegmentContactModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        segment_contact_list = [self.get_type(info, row) for row in rows]
        return SegmentContactListType(
            segment_contact_list=segment_contact_list, total=total
        )

    def insert_update(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = (
            kwargs.get("partition_key") or info.context.get("partition_key")
        )
        email = kwargs.get("email")

        try:
            if partition_key and email:
                # Update existing
                row = (
                    session.query(SegmentContactModel)
                    .filter(
                        SegmentContactModel.partition_key == partition_key,
                        SegmentContactModel.email == email,
                    )
                    .first()
                )
                if not row:
                    # Create new with explicit keys
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    # Update fields
                    field_map = [
                        "consumer_corp_external_id",
                        "contact_uuid",
                    ]
                    for field in field_map:
                        if field in kwargs:
                            val = kwargs[field]
                            setattr(
                                row,
                                field,
                                None if val == "null" else val,
                            )
                    row.updated_by = kwargs["updated_by"]
                    row.updated_at = pendulum.now("UTC")
            else:
                # Create new
                row = self._create_row(info, **kwargs)
                session.add(row)

            session.commit()
            session.refresh(row)
            return normalize_row(row)

        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def _create_row(
        self, info: ResolveInfo, **kwargs: Any
    ) -> SegmentContactModel:
        partition_key = (
            kwargs.get("partition_key") or info.context.get("partition_key")
        )
        email = kwargs.get("email")

        cols = {
            "partition_key": partition_key,
            "segment_uuid": kwargs.get("segment_uuid"),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in ["consumer_corp_external_id", "contact_uuid"]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if email:
            cols["email"] = email

        return SegmentContactModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = (
            kwargs.get("partition_key") or info.context.get("partition_key")
        )
        email = kwargs.get("email")

        try:
            row = (
                session.query(SegmentContactModel)
                .filter(
                    SegmentContactModel.partition_key == partition_key,
                    SegmentContactModel.email == email,
                )
                .first()
            )
            if not row:
                return True  # Already deleted

            session.delete(row)
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def get_type(self, info: ResolveInfo, row: Any) -> SegmentContactType:
        """Convert a SQLAlchemy row to SegmentContactType."""
        data = normalize_row(row)
        if data is None:
            return None
        return SegmentContactType(**normalize_to_json(data))

    def resolve_single(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[SegmentContactType]:
        """Resolve a single segment_contact, supporting segment_uuid + email lookup."""
        partition_key = info.context.get("partition_key")
        segment_uuid = kwargs.get("segment_uuid")
        email = kwargs.get("email")

        if segment_uuid and email:
            # Query by partition_key + segment_uuid + email
            session = Config.db_session
            row = (
                session.query(SegmentContactModel)
                .filter(
                    SegmentContactModel.partition_key == partition_key,
                    SegmentContactModel.segment_uuid == segment_uuid,
                    SegmentContactModel.email == email,
                )
                .first()
            )
            return self.get_type(info, row) if row else None

        if "email" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, email=kwargs["email"]
        )
        if count == 0:
            return None

        session = Config.db_session
        row = (
            session.query(SegmentContactModel)
            .filter(
                SegmentContactModel.partition_key == partition_key,
                SegmentContactModel.email == kwargs["email"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["SegmentContactPGRepository"]