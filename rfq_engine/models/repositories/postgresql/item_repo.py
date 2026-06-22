# -*- coding: utf-8 -*-
"""PostgreSQL repository for Item entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL ItemModel.
"""
from __future__ import print_function

__author__ = "bibow"

import functools
import traceback
from typing import Any, Dict, List, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.item import ItemListType, ItemType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.item import ItemModel


class ItemPGRepository(EntityRepository):
    """PostgreSQL repository for Item entity."""

    @property
    def entity_type(self) -> str:
        return "item"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        item_uuid = keys.get("item_uuid")
        if not partition_key or not item_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(ItemModel)
            .filter(
                ItemModel.partition_key == partition_key,
                ItemModel.item_uuid == item_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        item_uuid = keys.get("item_uuid")
        if not partition_key or not item_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(ItemModel)
            .filter(
                ItemModel.partition_key == partition_key,
                ItemModel.item_uuid == item_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated item list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        item_type = filters.get("item_type")
        item_name = filters.get("item_name")
        item_description = filters.get("item_description")
        pricing_mode = filters.get("pricing_mode")
        uoms = filters.get("uoms")

        query = session.query(ItemModel)
        if partition_key:
            query = query.filter(ItemModel.partition_key == partition_key)
        if item_type:
            query = query.filter(ItemModel.item_type == item_type)
        if item_name:
            query = query.filter(ItemModel.item_name.ilike(f"%{item_name}%"))
        if item_description:
            query = query.filter(
                ItemModel.item_description.ilike(f"%{item_description}%")
            )
        if pricing_mode:
            query = query.filter(ItemModel.pricing_mode == pricing_mode)
        if uoms:
            query = query.filter(ItemModel.uom.in_(uoms))

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(ItemModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        item_list = [self.get_type(info, row) for row in rows]
        return ItemListType(item_list=item_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        item_uuid = kwargs.get("item_uuid")

        try:
            if item_uuid:
                # Update existing
                row = (
                    session.query(ItemModel)
                    .filter(
                        ItemModel.partition_key == partition_key,
                        ItemModel.item_uuid == item_uuid,
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
                        "item_type",
                        "item_name",
                        "item_description",
                        "pricing_mode",
                        "uom",
                        "item_external_id",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> ItemModel:
        partition_key = info.context.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")
        item_uuid = kwargs.get("item_uuid")

        cols = {
            "partition_key": partition_key,
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "item_type",
            "item_name",
            "item_description",
            "pricing_mode",
            "uom",
            "item_external_id",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if item_uuid:
            cols["item_uuid"] = item_uuid

        return ItemModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        item_uuid = kwargs.get("item_uuid")

        try:
            # Check for dependent provider_items
            from ...postgresql.provider_item import ProviderItemModel

            dep_count = (
                session.query(ProviderItemModel)
                .filter(
                    ProviderItemModel.partition_key == partition_key,
                    ProviderItemModel.item_uuid == item_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            row = (
                session.query(ItemModel)
                .filter(
                    ItemModel.partition_key == partition_key,
                    ItemModel.item_uuid == item_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> ItemType:
        """Convert a SQLAlchemy row to ItemType."""
        data = normalize_row(row)
        if data is None:
            return None
        return ItemType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[ItemType]:
        """Resolve a single item, supporting item_external_id lookup."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if kwargs.get("item_external_id"):
            row = (
                session.query(ItemModel)
                .filter(
                    ItemModel.partition_key == partition_key,
                    ItemModel.item_external_id == kwargs["item_external_id"],
                )
                .first()
            )
            return self.get_type(info, row) if row else None

        if "item_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, item_uuid=kwargs["item_uuid"]
        )
        if count == 0:
            return None

        row = (
            session.query(ItemModel)
            .filter(
                ItemModel.partition_key == partition_key,
                ItemModel.item_uuid == kwargs["item_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["ItemPGRepository"]