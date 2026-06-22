# -*- coding: utf-8 -*-
"""PostgreSQL repository for Bundle entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL BundleModel. Delete is guarded by a
bundle_component dependency check.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.bundle import BundleListType, BundleType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.bundle import BundleModel


class BundlePGRepository(EntityRepository):
    """PostgreSQL repository for Bundle entity."""

    @property
    def entity_type(self) -> str:
        return "bundle"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        bundle_uuid = keys.get("bundle_uuid")
        if not partition_key or not bundle_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(BundleModel)
            .filter(
                BundleModel.partition_key == partition_key,
                BundleModel.bundle_uuid == bundle_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        bundle_uuid = keys.get("bundle_uuid")
        if not partition_key or not bundle_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(BundleModel)
            .filter(
                BundleModel.partition_key == partition_key,
                BundleModel.bundle_uuid == bundle_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated bundle list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        bundle_code = filters.get("bundle_code")
        bundle_type = filters.get("bundle_type")
        status = filters.get("status")

        query = session.query(BundleModel)
        if partition_key:
            query = query.filter(BundleModel.partition_key == partition_key)
        if bundle_code:
            query = query.filter(BundleModel.bundle_code == bundle_code)
        if bundle_type:
            query = query.filter(BundleModel.bundle_type == bundle_type)
        if status:
            query = query.filter(BundleModel.status == status)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(BundleModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        bundle_list = [self.get_type(info, row) for row in rows]
        return BundleListType(bundle_list=bundle_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        bundle_uuid = kwargs.get("bundle_uuid")

        try:
            if bundle_uuid:
                # Update existing
                row = (
                    session.query(BundleModel)
                    .filter(
                        BundleModel.partition_key == partition_key,
                        BundleModel.bundle_uuid == bundle_uuid,
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
                        "bundle_code",
                        "bundle_name",
                        "bundle_type",
                        "description",
                        "extra",
                        "status",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> BundleModel:
        partition_key = info.context.get("partition_key")
        bundle_uuid = kwargs.get("bundle_uuid")

        cols = {
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "bundle_code",
            "bundle_name",
            "bundle_type",
            "description",
            "extra",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if bundle_uuid:
            cols["bundle_uuid"] = bundle_uuid

        return BundleModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        bundle_uuid = kwargs.get("bundle_uuid")

        try:
            # Check for dependent bundle_components
            from ...postgresql.bundle_component import BundleComponentModel

            dep_count = (
                session.query(BundleComponentModel)
                .filter(
                    BundleComponentModel.partition_key == partition_key,
                    BundleComponentModel.bundle_uuid == bundle_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            row = (
                session.query(BundleModel)
                .filter(
                    BundleModel.partition_key == partition_key,
                    BundleModel.bundle_uuid == bundle_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> BundleType:
        """Convert a SQLAlchemy row to BundleType."""
        data = normalize_row(row)
        if data is None:
            return None
        return BundleType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[BundleType]:
        """Resolve a single bundle by bundle_uuid."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if "bundle_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, bundle_uuid=kwargs["bundle_uuid"]
        )
        if count == 0:
            return None

        row = (
            session.query(BundleModel)
            .filter(
                BundleModel.partition_key == partition_key,
                BundleModel.bundle_uuid == kwargs["bundle_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["BundlePGRepository"]