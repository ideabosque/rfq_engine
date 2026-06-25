# -*- coding: utf-8 -*-
"""PostgreSQL repository for Request entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL RequestModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.request import RequestListType, RequestType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.request import RequestModel


class RequestPGRepository(EntityRepository):
    """PostgreSQL repository for Request entity."""

    @property
    def entity_type(self) -> str:
        return "request"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        request_uuid = keys.get("request_uuid")
        if not partition_key or not request_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(RequestModel)
            .filter(
                RequestModel.partition_key == partition_key,
                RequestModel.request_uuid == request_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        request_uuid = keys.get("request_uuid")
        if not partition_key or not request_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(RequestModel)
            .filter(
                RequestModel.partition_key == partition_key,
                RequestModel.request_uuid == request_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated request list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        email = filters.get("email")
        request_title = filters.get("request_title")
        request_description = filters.get("request_description")
        statuses = filters.get("statuses")
        bundle_uuid = filters.get("bundle_uuid")

        query = session.query(RequestModel)
        if partition_key:
            query = query.filter(RequestModel.partition_key == partition_key)
        if email:
            query = query.filter(RequestModel.email == email)
        if request_title:
            query = query.filter(
                RequestModel.request_title.ilike(f"%{request_title}%")
            )
        if request_description:
            query = query.filter(
                RequestModel.request_description.ilike(f"%{request_description}%")
            )
        if statuses:
            query = query.filter(RequestModel.status.in_(statuses))
        if bundle_uuid:
            query = query.filter(RequestModel.bundle_uuid == bundle_uuid)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(RequestModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        request_list = [self.get_type(info, row) for row in rows]
        return RequestListType(request_list=request_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        request_uuid = kwargs.get("request_uuid")

        try:
            if request_uuid:
                # Update existing
                row = (
                    session.query(RequestModel)
                    .filter(
                        RequestModel.partition_key == partition_key,
                        RequestModel.request_uuid == request_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "email",
                        "request_title",
                        "request_description",
                        "billing_address",
                        "shipping_address",
                        "items",
                        "notes",
                        "bundle_uuid",
                        "status",
                        "expired_at",
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
        finally:
            Config.db_session.remove()

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> RequestModel:
        partition_key = info.context.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")

        cols = {
            "partition_key": partition_key,
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "items": kwargs.get("items", []),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "email",
            "request_title",
            "request_description",
            "billing_address",
            "shipping_address",
            "items",
            "notes",
            "bundle_uuid",
            "status",
            "expired_at",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        request_uuid = kwargs.get("request_uuid")
        if request_uuid:
            cols["request_uuid"] = request_uuid

        return RequestModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        request_uuid = kwargs.get("request_uuid")

        try:
            # Check for dependent quotes
            from ...postgresql.quote import QuoteModel

            dep_count = (
                session.query(QuoteModel)
                .filter(
                    QuoteModel.partition_key == partition_key,
                    QuoteModel.request_uuid == request_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            # Check for dependent files
            from ...postgresql.file import FileModel

            dep_count = (
                session.query(FileModel)
                .filter(
                    FileModel.partition_key == partition_key,
                    FileModel.request_uuid == request_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            row = (
                session.query(RequestModel)
                .filter(
                    RequestModel.partition_key == partition_key,
                    RequestModel.request_uuid == request_uuid,
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
        finally:
            Config.db_session.remove()

    def get_type(self, info: ResolveInfo, row: Any) -> RequestType | None:
        """Convert a SQLAlchemy row to RequestType."""
        data = normalize_row(row)
        if data is None:
            return None
        return RequestType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[RequestType]:
        """Resolve a single request by partition_key and request_uuid."""
        partition_key = info.context.get("partition_key")
        request_uuid = kwargs.get("request_uuid")
        if not request_uuid:
            return None

        count = self.count(
            partition_key=partition_key, request_uuid=request_uuid
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(RequestModel)
            .filter(
                RequestModel.partition_key == partition_key,
                RequestModel.request_uuid == request_uuid,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["RequestPGRepository"]