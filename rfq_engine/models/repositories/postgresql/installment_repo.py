# -*- coding: utf-8 -*-
"""PostgreSQL repository for Installment entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL InstallmentModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.installment import InstallmentListType, InstallmentType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.installment import InstallmentModel


class InstallmentPGRepository(EntityRepository):
    """PostgreSQL repository for Installment entity."""

    @property
    def entity_type(self) -> str:
        return "installment"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        quote_uuid = keys.get("quote_uuid")
        installment_uuid = keys.get("installment_uuid")
        if not quote_uuid or not installment_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(InstallmentModel)
            .filter(
                InstallmentModel.quote_uuid == quote_uuid,
                InstallmentModel.installment_uuid == installment_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        quote_uuid = keys.get("quote_uuid")
        installment_uuid = keys.get("installment_uuid")
        if not quote_uuid or not installment_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(InstallmentModel)
            .filter(
                InstallmentModel.quote_uuid == quote_uuid,
                InstallmentModel.installment_uuid == installment_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated installment list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        quote_uuid = filters.get("quote_uuid")
        request_uuid = filters.get("request_uuid")
        status = filters.get("status")

        query = session.query(InstallmentModel)
        if quote_uuid:
            query = query.filter(InstallmentModel.quote_uuid == quote_uuid)
        if request_uuid:
            query = query.filter(InstallmentModel.request_uuid == request_uuid)
        if partition_key:
            query = query.filter(InstallmentModel.partition_key == partition_key)
        if status:
            query = query.filter(InstallmentModel.status == status)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(InstallmentModel.priority.asc())
            .order_by(InstallmentModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        installment_list = [self.get_type(info, row) for row in rows]
        return InstallmentListType(
            installment_list=installment_list, total=total
        )

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        quote_uuid = kwargs.get("quote_uuid")
        installment_uuid = kwargs.get("installment_uuid")

        try:
            if installment_uuid:
                # Update existing
                row = (
                    session.query(InstallmentModel)
                    .filter(
                        InstallmentModel.quote_uuid == quote_uuid,
                        InstallmentModel.installment_uuid == installment_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "partition_key",
                        "request_uuid",
                        "priority",
                        "salesorder_no",
                        "payment_method",
                        "scheduled_date",
                        "installment_ratio",
                        "installment_amount",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> InstallmentModel:
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        quote_uuid = kwargs.get("quote_uuid")
        request_uuid = kwargs.get("request_uuid")

        cols = {
            "quote_uuid": quote_uuid,
            "partition_key": partition_key,
            "priority": kwargs.get("priority", 0),
            "installment_ratio": kwargs.get("installment_ratio", 0),
            "installment_amount": kwargs.get("installment_amount", 0),
            "status": kwargs.get("status", "pending"),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "partition_key",
            "request_uuid",
            "priority",
            "salesorder_no",
            "payment_method",
            "scheduled_date",
            "installment_ratio",
            "installment_amount",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        # Auto-calculate installment_ratio from the parent quote's
        # final_total_quote_amount when the caller didn't supply a ratio.
        if not cols.get("installment_ratio") and request_uuid and quote_uuid:
            ratio = self._calculate_installment_ratio(
                info, request_uuid, quote_uuid, float(cols.get("installment_amount") or 0)
            )
            if ratio is not None:
                cols["installment_ratio"] = ratio

        installment_uuid = kwargs.get("installment_uuid")
        if installment_uuid:
            cols["installment_uuid"] = installment_uuid

        return InstallmentModel(**cols)

    def _calculate_installment_ratio(
        self,
        info: ResolveInfo,
        request_uuid: str,
        quote_uuid: str,
        installment_amount: float,
    ) -> Optional[float]:
        """Return ``installment_ratio`` as a percentage of the quote final total."""
        from ...postgresql.quote import QuoteModel

        session = Config.db_session
        quote = (
            session.query(QuoteModel)
            .filter(
                QuoteModel.request_uuid == request_uuid,
                QuoteModel.quote_uuid == quote_uuid,
            )
            .first()
        )
        if quote is None:
            return None
        final_total = float(quote.final_total_quote_amount or 0)
        if final_total > 0:
            return (installment_amount / final_total) * 100
        return None

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        quote_uuid = kwargs.get("quote_uuid")
        installment_uuid = kwargs.get("installment_uuid")

        try:
            # No child dependencies for installments
            row = (
                session.query(InstallmentModel)
                .filter(
                    InstallmentModel.quote_uuid == quote_uuid,
                    InstallmentModel.installment_uuid == installment_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> InstallmentType:
        """Convert a SQLAlchemy row to InstallmentType."""
        data = normalize_row(row)
        if data is None:
            return None
        return InstallmentType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[InstallmentType]:
        """Resolve a single installment by quote_uuid and installment_uuid."""
        quote_uuid = kwargs.get("quote_uuid")
        installment_uuid = kwargs.get("installment_uuid")
        if not quote_uuid or not installment_uuid:
            return None

        count = self.count(
            quote_uuid=quote_uuid, installment_uuid=installment_uuid
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(InstallmentModel)
            .filter(
                InstallmentModel.quote_uuid == quote_uuid,
                InstallmentModel.installment_uuid == installment_uuid,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["InstallmentPGRepository"]