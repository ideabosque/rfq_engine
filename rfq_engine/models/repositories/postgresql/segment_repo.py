# -*- coding: utf-8 -*-
"""PostgreSQL repository for Segment entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL SegmentModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.segment import SegmentListType, SegmentType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.segment import SegmentModel


class SegmentPGRepository(EntityRepository):
    """PostgreSQL repository for Segment entity."""

    @property
    def entity_type(self) -> str:
        return "segment"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        segment_uuid = keys.get("segment_uuid")
        if not partition_key or not segment_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(SegmentModel)
            .filter(
                SegmentModel.partition_key == partition_key,
                SegmentModel.segment_uuid == segment_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        segment_uuid = keys.get("segment_uuid")
        if not partition_key or not segment_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(SegmentModel)
            .filter(
                SegmentModel.partition_key == partition_key,
                SegmentModel.segment_uuid == segment_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated segment list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        provider_corp_external_id = filters.get("provider_corp_external_id")
        segment_name = filters.get("segment_name")
        segment_description = filters.get("segment_description")

        query = session.query(SegmentModel)
        if partition_key:
            query = query.filter(SegmentModel.partition_key == partition_key)
        if provider_corp_external_id:
            query = query.filter(
                SegmentModel.provider_corp_external_id
                == provider_corp_external_id
            )
        if segment_name:
            query = query.filter(
                SegmentModel.segment_name.ilike(f"%{segment_name}%")
            )
        if segment_description:
            query = query.filter(
                SegmentModel.segment_description.ilike(
                    f"%{segment_description}%"
                )
            )

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(SegmentModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        segment_list = [self.get_type(info, row) for row in rows]
        return SegmentListType(segment_list=segment_list, total=total)

    def insert_update(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        segment_uuid = kwargs.get("segment_uuid")

        try:
            if segment_uuid:
                # Update existing
                row = (
                    session.query(SegmentModel)
                    .filter(
                        SegmentModel.partition_key == partition_key,
                        SegmentModel.segment_uuid == segment_uuid,
                    )
                    .first()
                )
                if not row:
                    # Create new with explicit UUID
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    # Update fields
                    field_map = [
                        "provider_corp_external_id",
                        "segment_name",
                        "segment_description",
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
                # Create new with server-generated UUID
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> SegmentModel:
        partition_key = info.context.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")
        segment_uuid = kwargs.get("segment_uuid")

        cols = {
            "partition_key": partition_key,
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "provider_corp_external_id",
            "segment_name",
            "segment_description",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if segment_uuid:
            cols["segment_uuid"] = segment_uuid

        return SegmentModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        segment_uuid = kwargs.get("segment_uuid")

        try:
            # Check for dependent segment_contacts
            from ...postgresql.segment_contact import SegmentContactModel

            dep_count = (
                session.query(SegmentContactModel)
                .filter(
                    SegmentContactModel.partition_key == partition_key,
                    SegmentContactModel.segment_uuid == segment_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            row = (
                session.query(SegmentModel)
                .filter(
                    SegmentModel.partition_key == partition_key,
                    SegmentModel.segment_uuid == segment_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> SegmentType | None:
        """Convert a SQLAlchemy row to SegmentType."""
        data = normalize_row(row)
        if data is None:
            return None
        return SegmentType(**normalize_to_json(data))

    def resolve_single(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[SegmentType]:
        """Resolve a single segment by segment_uuid."""
        partition_key = info.context.get("partition_key")

        if "segment_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, segment_uuid=kwargs["segment_uuid"]
        )
        if count == 0:
            return None

        session = Config.db_session
        row = (
            session.query(SegmentModel)
            .filter(
                SegmentModel.partition_key == partition_key,
                SegmentModel.segment_uuid == kwargs["segment_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["SegmentPGRepository"]