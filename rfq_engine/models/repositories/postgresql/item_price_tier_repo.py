# -*- coding: utf-8 -*-
"""PostgreSQL repository for ItemPriceTier entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL ItemPriceTierModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.item_price_tier import ItemPriceTierListType, ItemPriceTierType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.item_price_tier import ItemPriceTierModel


class ItemPriceTierPGRepository(EntityRepository):
    """PostgreSQL repository for ItemPriceTier entity."""

    @property
    def entity_type(self) -> str:
        return "item_price_tier"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        item_uuid = keys.get("item_uuid")
        item_price_tier_uuid = keys.get("item_price_tier_uuid")
        if not item_uuid or not item_price_tier_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(ItemPriceTierModel)
            .filter(
                ItemPriceTierModel.item_uuid == item_uuid,
                ItemPriceTierModel.item_price_tier_uuid == item_price_tier_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        item_uuid = keys.get("item_uuid")
        item_price_tier_uuid = keys.get("item_price_tier_uuid")
        if not item_uuid or not item_price_tier_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(ItemPriceTierModel)
            .filter(
                ItemPriceTierModel.item_uuid == item_uuid,
                ItemPriceTierModel.item_price_tier_uuid == item_price_tier_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated item price tier list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        item_uuid = filters.get("item_uuid")
        provider_item_uuid = filters.get("provider_item_uuid")
        segment_uuid = filters.get("segment_uuid")
        partition_key = info.context.get("partition_key")
        status = filters.get("status")
        pax_type = filters.get("pax_type")
        quantity_value = filters.get("quantity_value")
        max_price = filters.get("max_price")
        min_price = filters.get("min_price")

        query = session.query(ItemPriceTierModel)
        if item_uuid:
            query = query.filter(ItemPriceTierModel.item_uuid == item_uuid)
        if provider_item_uuid:
            query = query.filter(
                ItemPriceTierModel.provider_item_uuid == provider_item_uuid
            )
        if segment_uuid:
            query = query.filter(ItemPriceTierModel.segment_uuid == segment_uuid)
        if partition_key:
            query = query.filter(ItemPriceTierModel.partition_key == partition_key)
        if status:
            query = query.filter(ItemPriceTierModel.status == status)
        if pax_type:
            query = query.filter(ItemPriceTierModel.pax_type == pax_type)
        if quantity_value is not None:
            query = query.filter(
                ItemPriceTierModel.quantity_greater_then <= quantity_value
            )
            # quantity_less_then is nullable (no upper limit) or > quantity_value
            query = query.filter(
                (ItemPriceTierModel.quantity_less_then.is_(None))
                | (ItemPriceTierModel.quantity_less_then > quantity_value)
            )
        if max_price and min_price:
            query = query.filter(
                ItemPriceTierModel.price_per_uom.between(min_price, max_price)
            )

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(ItemPriceTierModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        tier_list = [self.get_type(info, row) for row in rows]
        return ItemPriceTierListType(item_price_tier_list=tier_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        item_uuid = kwargs.get("item_uuid")
        item_price_tier_uuid = kwargs.get("item_price_tier_uuid")

        try:
            if item_price_tier_uuid:
                # Update existing
                row = (
                    session.query(ItemPriceTierModel)
                    .filter(
                        ItemPriceTierModel.item_uuid == item_uuid,
                        ItemPriceTierModel.item_price_tier_uuid == item_price_tier_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "provider_item_uuid",
                        "segment_uuid",
                        "partition_key",
                        "quantity_greater_then",
                        "quantity_less_then",
                        "pax_type",
                        "margin_per_uom",
                        "price_per_uom",
                        "currency",
                        "base_occupancy",
                        "extra_pax_surcharges",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> ItemPriceTierModel:
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        item_uuid = kwargs.get("item_uuid")

        cols = {
            "item_uuid": item_uuid,
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "provider_item_uuid",
            "segment_uuid",
            "quantity_greater_then",
            "quantity_less_then",
            "pax_type",
            "margin_per_uom",
            "price_per_uom",
            "currency",
            "base_occupancy",
            "extra_pax_surcharges",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        item_price_tier_uuid = kwargs.get("item_price_tier_uuid")
        if item_price_tier_uuid:
            cols["item_price_tier_uuid"] = item_price_tier_uuid

        return ItemPriceTierModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        item_uuid = kwargs.get("item_uuid")
        item_price_tier_uuid = kwargs.get("item_price_tier_uuid")

        try:
            # No child dependencies for item price tiers
            row = (
                session.query(ItemPriceTierModel)
                .filter(
                    ItemPriceTierModel.item_uuid == item_uuid,
                    ItemPriceTierModel.item_price_tier_uuid == item_price_tier_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> ItemPriceTierType | None:
        """Convert a SQLAlchemy row to ItemPriceTierType."""
        data = normalize_row(row)
        if data is None:
            return None
        return ItemPriceTierType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[ItemPriceTierType]:
        """Resolve a single item price tier by item_uuid and item_price_tier_uuid."""
        item_uuid = kwargs.get("item_uuid")
        item_price_tier_uuid = kwargs.get("item_price_tier_uuid")
        if not item_uuid or not item_price_tier_uuid:
            return None

        count = self.count(
            item_uuid=item_uuid, item_price_tier_uuid=item_price_tier_uuid
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(ItemPriceTierModel)
            .filter(
                ItemPriceTierModel.item_uuid == item_uuid,
                ItemPriceTierModel.item_price_tier_uuid == item_price_tier_uuid,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["ItemPriceTierPGRepository"]