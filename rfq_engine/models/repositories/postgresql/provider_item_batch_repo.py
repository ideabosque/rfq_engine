# -*- coding: utf-8 -*-
"""PostgreSQL repository for ProviderItemBatch entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL ProviderItemBatchModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.provider_item_batches import (
    ProviderItemBatchListType,
    ProviderItemBatchType,
)
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.provider_item_batch import ProviderItemBatchModel


def _validate_service_window(service_start_at: Any, service_end_at: Any) -> None:
    if service_start_at in (None, "null") or service_end_at in (None, "null"):
        return
    if service_end_at <= service_start_at:
        raise ValueError("service_end_at must be later than service_start_at")


class ProviderItemBatchPGRepository(EntityRepository):
    """PostgreSQL repository for ProviderItemBatch entity."""

    @property
    def entity_type(self) -> str:
        return "provider_item_batch"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        provider_item_uuid = keys.get("provider_item_uuid")
        batch_no = keys.get("batch_no")
        if not provider_item_uuid or not batch_no:
            return None
        session = Config.db_session
        row = (
            session.query(ProviderItemBatchModel)
            .filter(
                ProviderItemBatchModel.provider_item_uuid
                == provider_item_uuid,
                ProviderItemBatchModel.batch_no == batch_no,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        provider_item_uuid = keys.get("provider_item_uuid")
        batch_no = keys.get("batch_no")
        if not provider_item_uuid or not batch_no:
            return 0
        session = Config.db_session
        return (
            session.query(ProviderItemBatchModel)
            .filter(
                ProviderItemBatchModel.provider_item_uuid
                == provider_item_uuid,
                ProviderItemBatchModel.batch_no == batch_no,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated provider_item_batch list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        provider_item_uuid = filters.get("provider_item_uuid")
        item_uuid = filters.get("item_uuid")
        expired_at_gt = filters.get("expired_at_gt")
        expired_at_lt = filters.get("expired_at_lt")
        produced_at_gt = filters.get("produced_at_gt")
        produced_at_lt = filters.get("produced_at_lt")
        min_cost_per_uom = filters.get("min_cost_per_uom")
        max_cost_per_uom = filters.get("max_cost_per_uom")
        min_total_cost_per_uom = filters.get("min_total_cost_per_uom")
        max_total_cost_per_uom = filters.get("max_total_cost_per_uom")
        slow_move_item = filters.get("slow_move_item")
        in_stock = filters.get("in_stock")
        service_start_at_gt = filters.get("service_start_at_gt")
        service_start_at_lt = filters.get("service_start_at_lt")
        service_end_at_gt = filters.get("service_end_at_gt")
        service_end_at_lt = filters.get("service_end_at_lt")
        service_window_start = filters.get("service_window_start")
        service_window_end = filters.get("service_window_end")
        updated_at_gt = filters.get("updated_at_gt")
        updated_at_lt = filters.get("updated_at_lt")

        if (service_window_start is None) != (service_window_end is None):
            raise ValueError(
                "service_window_start and service_window_end must be provided together"
            )
        _validate_service_window(service_window_start, service_window_end)

        query = session.query(ProviderItemBatchModel)
        if provider_item_uuid:
            query = query.filter(
                ProviderItemBatchModel.provider_item_uuid
                == provider_item_uuid
            )
        if partition_key:
            query = query.filter(
                ProviderItemBatchModel.partition_key == partition_key
            )
        if item_uuid:
            query = query.filter(
                ProviderItemBatchModel.item_uuid == item_uuid
            )
        if expired_at_gt:
            query = query.filter(
                ProviderItemBatchModel.expired_at >= expired_at_gt
            )
        if expired_at_lt:
            query = query.filter(
                ProviderItemBatchModel.expired_at < expired_at_lt
            )
        if produced_at_gt:
            query = query.filter(
                ProviderItemBatchModel.produced_at >= produced_at_gt
            )
        if produced_at_lt:
            query = query.filter(
                ProviderItemBatchModel.produced_at < produced_at_lt
            )
        if min_cost_per_uom:
            query = query.filter(
                ProviderItemBatchModel.cost_per_uom >= min_cost_per_uom
            )
        if max_cost_per_uom:
            query = query.filter(
                ProviderItemBatchModel.cost_per_uom <= max_cost_per_uom
            )
        if min_total_cost_per_uom:
            query = query.filter(
                ProviderItemBatchModel.total_cost_per_uom
                >= min_total_cost_per_uom
            )
        if max_total_cost_per_uom:
            query = query.filter(
                ProviderItemBatchModel.total_cost_per_uom
                <= max_total_cost_per_uom
            )
        if slow_move_item is not None:
            query = query.filter(
                ProviderItemBatchModel.slow_move_item == slow_move_item
            )
        if in_stock is not None:
            query = query.filter(
                ProviderItemBatchModel.in_stock == in_stock
            )
        if service_start_at_gt:
            query = query.filter(
                ProviderItemBatchModel.service_start_at >= service_start_at_gt
            )
        if service_start_at_lt:
            query = query.filter(
                ProviderItemBatchModel.service_start_at < service_start_at_lt
            )
        if service_end_at_gt:
            query = query.filter(
                ProviderItemBatchModel.service_end_at >= service_end_at_gt
            )
        if service_end_at_lt:
            query = query.filter(
                ProviderItemBatchModel.service_end_at < service_end_at_lt
            )
        if service_window_start is not None:
            query = query.filter(
                ProviderItemBatchModel.service_start_at < service_window_end
            )
            query = query.filter(
                ProviderItemBatchModel.service_end_at > service_window_start
            )
        if updated_at_gt:
            query = query.filter(
                ProviderItemBatchModel.updated_at > updated_at_gt
            )
        if updated_at_lt:
            query = query.filter(
                ProviderItemBatchModel.updated_at < updated_at_lt
            )

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(ProviderItemBatchModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        batch_list = [self.get_type(info, row) for row in rows]
        return ProviderItemBatchListType(
            provider_item_batch_list=batch_list, total=total
        )

    def insert_update(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        provider_item_uuid = kwargs.get("provider_item_uuid")
        batch_no = kwargs.get("batch_no")

        try:
            if provider_item_uuid and batch_no:
                # Update existing
                row = (
                    session.query(ProviderItemBatchModel)
                    .filter(
                        ProviderItemBatchModel.provider_item_uuid
                        == provider_item_uuid,
                        ProviderItemBatchModel.batch_no == batch_no,
                    )
                    .first()
                )
                if not row:
                    # Create new with explicit keys
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    _validate_service_window(
                        kwargs.get(
                            "service_start_at", row.service_start_at
                        ),
                        kwargs.get("service_end_at", row.service_end_at),
                    )
                    # Update fields
                    field_map = [
                        "item_uuid",
                        "expired_at",
                        "produced_at",
                        "service_start_at",
                        "service_end_at",
                        "cost_per_uom",
                        "freight_cost_per_uom",
                        "additional_cost_per_uom",
                        "total_cost_per_uom",
                        "guardrail_margin_per_uom",
                        "guardrail_price_per_uom",
                        "slow_move_item",
                        "in_stock",
                        "availability_qty",
                        "currency",
                        "cancellation_policy_uuid",
                    ]
                    for field in field_map:
                        if field in kwargs:
                            val = kwargs[field]
                            setattr(
                                row,
                                field,
                                None if val == "null" else val,
                            )

                    # Recalculate derived fields
                    cost_per_uom = float(
                        kwargs.get("cost_per_uom", row.cost_per_uom or 0)
                    )
                    freight_cost_per_uom = float(
                        kwargs.get(
                            "freight_cost_per_uom",
                            row.freight_cost_per_uom or 0,
                        )
                    )
                    additional_cost_per_uom = float(
                        kwargs.get(
                            "additional_cost_per_uom",
                            row.additional_cost_per_uom or 0,
                        )
                    )
                    row.total_cost_per_uom = (
                        cost_per_uom
                        + freight_cost_per_uom
                        + additional_cost_per_uom
                    )

                    guardrail_margin_per_uom = float(
                        kwargs.get(
                            "guardrail_margin_per_uom",
                            row.guardrail_margin_per_uom or 0,
                        )
                    )
                    row.guardrail_price_per_uom = row.total_cost_per_uom * (
                        1 + guardrail_margin_per_uom / 100
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
    ) -> ProviderItemBatchModel:
        _validate_service_window(
            kwargs.get("service_start_at"), kwargs.get("service_end_at")
        )

        cols = {
            "partition_key": info.context.get("partition_key"),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "item_uuid",
            "expired_at",
            "produced_at",
            "service_start_at",
            "service_end_at",
            "cost_per_uom",
            "freight_cost_per_uom",
            "additional_cost_per_uom",
            "guardrail_margin_per_uom",
            "slow_move_item",
            "in_stock",
            "availability_qty",
            "currency",
            "cancellation_policy_uuid",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        # Calculate derived fields
        cost_per_uom = float(cols.get("cost_per_uom", 0) or 0)
        freight_cost_per_uom = float(cols.get("freight_cost_per_uom", 0) or 0)
        additional_cost_per_uom = float(
            cols.get("additional_cost_per_uom", 0) or 0
        )
        cols["total_cost_per_uom"] = (
            cost_per_uom + freight_cost_per_uom + additional_cost_per_uom
        )

        guardrail_margin_per_uom = float(
            cols.get("guardrail_margin_per_uom", 0) or 0
        )
        cols["guardrail_price_per_uom"] = cols["total_cost_per_uom"] * (
            1 + guardrail_margin_per_uom
        )

        if kwargs.get("provider_item_uuid"):
            cols["provider_item_uuid"] = kwargs["provider_item_uuid"]
        if kwargs.get("batch_no"):
            cols["batch_no"] = kwargs["batch_no"]

        return ProviderItemBatchModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        provider_item_uuid = kwargs.get("provider_item_uuid")
        batch_no = kwargs.get("batch_no")

        try:
            row = (
                session.query(ProviderItemBatchModel)
                .filter(
                    ProviderItemBatchModel.provider_item_uuid
                    == provider_item_uuid,
                    ProviderItemBatchModel.batch_no == batch_no,
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

    def get_type(self, info: ResolveInfo, row: Any) -> ProviderItemBatchType | None:
        """Convert a SQLAlchemy row to ProviderItemBatchType."""
        data = normalize_row(row)
        if data is None:
            return None
        return ProviderItemBatchType(**normalize_to_json(data))

    def resolve_single(
        self, info: ResolveInfo, **kwargs: Any
    ) -> Optional[ProviderItemBatchType]:
        """Resolve a single provider_item_batch by (provider_item_uuid, batch_no)."""
        provider_item_uuid = kwargs.get("provider_item_uuid")
        batch_no = kwargs.get("batch_no")
        if not provider_item_uuid or not batch_no:
            return None

        count = self.count(
            provider_item_uuid=provider_item_uuid, batch_no=batch_no
        )
        if count == 0:
            return None

        session = Config.db_session
        row = (
            session.query(ProviderItemBatchModel)
            .filter(
                ProviderItemBatchModel.provider_item_uuid
                == provider_item_uuid,
                ProviderItemBatchModel.batch_no == batch_no,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["ProviderItemBatchPGRepository"]