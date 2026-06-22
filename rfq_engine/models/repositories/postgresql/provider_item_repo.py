# -*- coding: utf-8 -*-
"""PostgreSQL repository for ProviderItem entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL ProviderItemModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.provider_item import (
    ProviderItemListType,
    ProviderItemType,
)
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.provider_item import ProviderItemModel


class ProviderItemPGRepository(EntityRepository):
    """PostgreSQL repository for ProviderItem entity."""

    @property
    def entity_type(self) -> str:
        return "provider_item"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        provider_item_uuid = keys.get("provider_item_uuid")
        if not partition_key or not provider_item_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(ProviderItemModel)
            .filter(
                ProviderItemModel.partition_key == partition_key,
                ProviderItemModel.provider_item_uuid == provider_item_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        provider_item_uuid = keys.get("provider_item_uuid")
        if not partition_key or not provider_item_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(ProviderItemModel)
            .filter(
                ProviderItemModel.partition_key == partition_key,
                ProviderItemModel.provider_item_uuid == provider_item_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated provider_item list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        item_uuid = filters.get("item_uuid")
        provider_corp_external_id = filters.get("provider_corp_external_id")
        provider_item_external_id = filters.get("provider_item_external_id")
        min_base_price_per_uom = filters.get("min_base_price_per_uom")
        max_base_price_per_uom = filters.get("max_base_price_per_uom")
        updated_at_gt = filters.get("updated_at_gt")
        updated_at_lt = filters.get("updated_at_lt")

        query = session.query(ProviderItemModel)
        if partition_key:
            query = query.filter(
                ProviderItemModel.partition_key == partition_key
            )
        if item_uuid:
            query = query.filter(ProviderItemModel.item_uuid == item_uuid)
        if provider_corp_external_id:
            query = query.filter(
                ProviderItemModel.provider_corp_external_id
                == provider_corp_external_id
            )
        if provider_item_external_id:
            query = query.filter(
                ProviderItemModel.provider_item_external_id
                == provider_item_external_id
            )
        if min_base_price_per_uom:
            query = query.filter(
                ProviderItemModel.base_price_per_uom >= min_base_price_per_uom
            )
        if max_base_price_per_uom:
            query = query.filter(
                ProviderItemModel.base_price_per_uom <= max_base_price_per_uom
            )
        if updated_at_gt:
            query = query.filter(ProviderItemModel.updated_at > updated_at_gt)
        if updated_at_lt:
            query = query.filter(ProviderItemModel.updated_at < updated_at_lt)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(ProviderItemModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        provider_item_list = [self.get_type(info, row) for row in rows]
        return ProviderItemListType(
            provider_item_list=provider_item_list, total=total
        )

    def insert_update(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        provider_item_uuid = kwargs.get("provider_item_uuid")

        availability_mode = kwargs.get(
            "availability_mode",
            getattr(kwargs.get("entity"), "availability_mode", "none") or "none",
        )
        if availability_mode not in {"none", "check_only", "require_hold"}:
            raise ValueError(
                "availability_mode must be one of: none, check_only, require_hold"
            )

        try:
            if provider_item_uuid:
                # Update existing
                row = (
                    session.query(ProviderItemModel)
                    .filter(
                        ProviderItemModel.partition_key == partition_key,
                        ProviderItemModel.provider_item_uuid
                        == provider_item_uuid,
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
                        "item_uuid",
                        "provider_corp_external_id",
                        "provider_item_external_id",
                        "base_price_per_uom",
                        "item_spec",
                        "availability_mode",
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

    def _create_row(
        self, info: ResolveInfo, **kwargs: Any
    ) -> ProviderItemModel:
        partition_key = info.context.get("partition_key")
        provider_item_uuid = kwargs.get("provider_item_uuid")

        cols = {
            "partition_key": partition_key,
            "item_spec": kwargs.get("item_spec", {}),
            "availability_mode": kwargs.get("availability_mode", "none"),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "item_uuid",
            "provider_corp_external_id",
            "provider_item_external_id",
            "base_price_per_uom",
            "item_spec",
            "availability_mode",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if provider_item_uuid:
            cols["provider_item_uuid"] = provider_item_uuid

        return ProviderItemModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        provider_item_uuid = kwargs.get("provider_item_uuid")

        try:
            # Check for dependent provider_item_batches
            from ...postgresql.provider_item_batch import ProviderItemBatchModel

            dep_count = (
                session.query(ProviderItemBatchModel)
                .filter(
                    ProviderItemBatchModel.provider_item_uuid
                    == provider_item_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            # Check for dependent item_price_tiers (if model exists)
            try:
                from ...postgresql.item_price_tier import ItemPriceTierModel

                tier_count = (
                    session.query(ItemPriceTierModel)
                    .filter(
                        ItemPriceTierModel.partition_key == partition_key,
                        ItemPriceTierModel.provider_item_uuid
                        == provider_item_uuid,
                    )
                    .count()
                )
                if tier_count > 0:
                    return False
            except ImportError:
                pass

            # Check for dependent quote_items (if model exists)
            try:
                from ...postgresql.quote_item import QuoteItemModel

                qi_count = (
                    session.query(QuoteItemModel)
                    .filter(
                        QuoteItemModel.partition_key == partition_key,
                        QuoteItemModel.provider_item_uuid
                        == provider_item_uuid,
                    )
                    .count()
                )
                if qi_count > 0:
                    return False
            except ImportError:
                pass

            row = (
                session.query(ProviderItemModel)
                .filter(
                    ProviderItemModel.partition_key == partition_key,
                    ProviderItemModel.provider_item_uuid
                    == provider_item_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> ProviderItemType:
        """Convert a SQLAlchemy row to ProviderItemType."""
        data = normalize_row(row)
        if data is None:
            return None
        return ProviderItemType(**normalize_to_json(data))

    def resolve_single(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[ProviderItemType]:
        """Resolve a single provider_item, supporting provider_item_external_id lookup."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if kwargs.get("provider_item_external_id"):
            row = (
                session.query(ProviderItemModel)
                .filter(
                    ProviderItemModel.partition_key == partition_key,
                    ProviderItemModel.provider_item_external_id
                    == kwargs["provider_item_external_id"],
                )
                .first()
            )
            return self.get_type(info, row) if row else None

        if "provider_item_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key,
            provider_item_uuid=kwargs["provider_item_uuid"],
        )
        if count == 0:
            return None

        row = (
            session.query(ProviderItemModel)
            .filter(
                ProviderItemModel.partition_key == partition_key,
                ProviderItemModel.provider_item_uuid
                == kwargs["provider_item_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["ProviderItemPGRepository"]