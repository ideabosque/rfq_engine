# -*- coding: utf-8 -*-
"""PostgreSQL repository for BundleComponent entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL BundleComponentModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.bundle_component import (
    BundleComponentListType,
    BundleComponentType,
)
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.bundle_component import BundleComponentModel


class BundleComponentPGRepository(EntityRepository):
    """PostgreSQL repository for BundleComponent entity."""

    @property
    def entity_type(self) -> str:
        return "bundle_component"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        bundle_component_uuid = keys.get("bundle_component_uuid")
        if not partition_key or not bundle_component_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(BundleComponentModel)
            .filter(
                BundleComponentModel.partition_key == partition_key,
                BundleComponentModel.bundle_component_uuid == bundle_component_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        bundle_component_uuid = keys.get("bundle_component_uuid")
        if not partition_key or not bundle_component_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(BundleComponentModel)
            .filter(
                BundleComponentModel.partition_key == partition_key,
                BundleComponentModel.bundle_component_uuid == bundle_component_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated bundle_component list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        bundle_uuid = filters.get("bundle_uuid")
        item_uuid = filters.get("item_uuid")
        provider_item_uuid = filters.get("provider_item_uuid")
        component_role = filters.get("component_role")
        status = filters.get("status")

        query = session.query(BundleComponentModel)
        if partition_key:
            query = query.filter(BundleComponentModel.partition_key == partition_key)
        if bundle_uuid:
            query = query.filter(BundleComponentModel.bundle_uuid == bundle_uuid)
        if item_uuid:
            query = query.filter(BundleComponentModel.item_uuid == item_uuid)
        if provider_item_uuid:
            query = query.filter(BundleComponentModel.provider_item_uuid == provider_item_uuid)
        if component_role:
            query = query.filter(BundleComponentModel.component_role == component_role)
        if status:
            query = query.filter(BundleComponentModel.status == status)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(BundleComponentModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        component_list = [self.get_type(info, row) for row in rows]
        return BundleComponentListType(bundle_component_list=component_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        bundle_component_uuid = kwargs.get("bundle_component_uuid")

        # Validate foreign-key references (mirrors DynamoDB validation logic)
        from ...postgresql.utils import (
            validate_bundle_exists,
            validate_item_exists,
            validate_provider_item_exists,
        )

        bundle_uuid = kwargs.get("bundle_uuid")
        if bundle_uuid and not validate_bundle_exists(partition_key, bundle_uuid):
            raise ValueError(f"bundle_uuid '{bundle_uuid}' does not exist")

        item_uuid = kwargs.get("item_uuid")
        if item_uuid and not validate_item_exists(partition_key, item_uuid):
            raise ValueError(f"item_uuid '{item_uuid}' does not exist")

        provider_item_uuid = kwargs.get("provider_item_uuid")
        if provider_item_uuid and not validate_provider_item_exists(
            partition_key, provider_item_uuid
        ):
            raise ValueError(f"provider_item_uuid '{provider_item_uuid}' does not exist")

        try:
            if bundle_component_uuid:
                # Update existing
                row = (
                    session.query(BundleComponentModel)
                    .filter(
                        BundleComponentModel.partition_key == partition_key,
                        BundleComponentModel.bundle_component_uuid == bundle_component_uuid,
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
                        "bundle_uuid",
                        "item_uuid",
                        "provider_item_uuid",
                        "component_role",
                        "required",
                        "default_qty",
                        "sort_order",
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
        finally:
            Config.db_session.remove()

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> BundleComponentModel:
        partition_key = info.context.get("partition_key")
        bundle_component_uuid = kwargs.get("bundle_component_uuid")

        cols = {
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "bundle_uuid",
            "item_uuid",
            "provider_item_uuid",
            "component_role",
            "required",
            "default_qty",
            "sort_order",
            "extra",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if bundle_component_uuid:
            cols["bundle_component_uuid"] = bundle_component_uuid

        return BundleComponentModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        bundle_component_uuid = kwargs.get("bundle_component_uuid")

        try:
            # No child dependencies for BundleComponent
            row = (
                session.query(BundleComponentModel)
                .filter(
                    BundleComponentModel.partition_key == partition_key,
                    BundleComponentModel.bundle_component_uuid == bundle_component_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> BundleComponentType | None:
        """Convert a SQLAlchemy row to BundleComponentType."""
        data = normalize_row(row)
        if data is None:
            return None
        return BundleComponentType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[BundleComponentType]:
        """Resolve a single bundle_component by bundle_component_uuid."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if "bundle_component_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key,
            bundle_component_uuid=kwargs["bundle_component_uuid"],
        )
        if count == 0:
            return None

        row = (
            session.query(BundleComponentModel)
            .filter(
                BundleComponentModel.partition_key == partition_key,
                BundleComponentModel.bundle_component_uuid == kwargs["bundle_component_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["BundleComponentPGRepository"]