# -*- coding: utf-8 -*-
"""PostgreSQL repository for FxRate entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL FxRateModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.fx_rate import FxRateListType, FxRateType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.fx_rate import FxRateModel


class FxRatePGRepository(EntityRepository):
    """PostgreSQL repository for FxRate entity."""

    @property
    def entity_type(self) -> str:
        return "fx_rate"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        fx_rate_uuid = keys.get("fx_rate_uuid")
        if not partition_key or not fx_rate_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(FxRateModel)
            .filter(
                FxRateModel.partition_key == partition_key,
                FxRateModel.fx_rate_uuid == fx_rate_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        fx_rate_uuid = keys.get("fx_rate_uuid")
        if not partition_key or not fx_rate_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(FxRateModel)
            .filter(
                FxRateModel.partition_key == partition_key,
                FxRateModel.fx_rate_uuid == fx_rate_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated fx_rate list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        source_currency = filters.get("source_currency")
        target_currency = filters.get("target_currency")
        status = filters.get("status")

        query = session.query(FxRateModel)
        if partition_key:
            query = query.filter(FxRateModel.partition_key == partition_key)
        if source_currency:
            query = query.filter(FxRateModel.source_currency == source_currency)
        if target_currency:
            query = query.filter(FxRateModel.target_currency == target_currency)
        if status:
            query = query.filter(FxRateModel.status == status)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(FxRateModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        fx_rate_list = [self.get_type(info, row) for row in rows]
        return FxRateListType(fx_rate_list=fx_rate_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        fx_rate_uuid = kwargs.get("fx_rate_uuid")

        try:
            if fx_rate_uuid:
                # Update existing
                row = (
                    session.query(FxRateModel)
                    .filter(
                        FxRateModel.partition_key == partition_key,
                        FxRateModel.fx_rate_uuid == fx_rate_uuid,
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
                        "source_currency",
                        "target_currency",
                        "rate",
                        "currency_pair_date",
                        "rate_date",
                        "provider",
                        "notes",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> FxRateModel:
        partition_key = info.context.get("partition_key")
        fx_rate_uuid = kwargs.get("fx_rate_uuid")

        cols = {
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "source_currency",
            "target_currency",
            "rate",
            "currency_pair_date",
            "rate_date",
            "provider",
            "notes",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if fx_rate_uuid:
            cols["fx_rate_uuid"] = fx_rate_uuid

        return FxRateModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        fx_rate_uuid = kwargs.get("fx_rate_uuid")

        try:
            # No child dependencies for FxRate
            row = (
                session.query(FxRateModel)
                .filter(
                    FxRateModel.partition_key == partition_key,
                    FxRateModel.fx_rate_uuid == fx_rate_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> FxRateType:
        """Convert a SQLAlchemy row to FxRateType."""
        data = normalize_row(row)
        if data is None:
            return None
        return FxRateType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[FxRateType]:
        """Resolve a single fx_rate by fx_rate_uuid."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if "fx_rate_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, fx_rate_uuid=kwargs["fx_rate_uuid"]
        )
        if count == 0:
            return None

        row = (
            session.query(FxRateModel)
            .filter(
                FxRateModel.partition_key == partition_key,
                FxRateModel.fx_rate_uuid == kwargs["fx_rate_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["FxRatePGRepository"]