# -*- coding: utf-8 -*-
"""PostgreSQL repository for Quote entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL QuoteModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.quote import QuoteListType, QuoteType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.quote import QuoteModel


class QuotePGRepository(EntityRepository):
    """PostgreSQL repository for Quote entity."""

    @property
    def entity_type(self) -> str:
        return "quote"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        request_uuid = keys.get("request_uuid")
        quote_uuid = keys.get("quote_uuid")
        if not request_uuid or not quote_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(QuoteModel)
            .filter(
                QuoteModel.request_uuid == request_uuid,
                QuoteModel.quote_uuid == quote_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        request_uuid = keys.get("request_uuid")
        quote_uuid = keys.get("quote_uuid")
        if not request_uuid or not quote_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(QuoteModel)
            .filter(
                QuoteModel.request_uuid == request_uuid,
                QuoteModel.quote_uuid == quote_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated quote list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        request_uuid = filters.get("request_uuid")
        provider_corp_external_id = filters.get("provider_corp_external_id")
        sales_rep_email = filters.get("sales_rep_email")
        status = filters.get("status")
        statuses = filters.get("statuses")

        query = session.query(QuoteModel)
        if request_uuid:
            query = query.filter(QuoteModel.request_uuid == request_uuid)
        if provider_corp_external_id:
            query = query.filter(
                QuoteModel.provider_corp_external_id == provider_corp_external_id
            )
        if sales_rep_email:
            query = query.filter(QuoteModel.sales_rep_email == sales_rep_email)
        if partition_key:
            query = query.filter(QuoteModel.partition_key == partition_key)
        if status:
            query = query.filter(QuoteModel.status == status)
        if statuses:
            query = query.filter(QuoteModel.status.in_(statuses))

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(QuoteModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        quote_list = [self.get_type(info, row) for row in rows]
        return QuoteListType(quote_list=quote_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        request_uuid = kwargs.get("request_uuid")
        quote_uuid = kwargs.get("quote_uuid")

        try:
            if quote_uuid:
                # Update existing
                row = (
                    session.query(QuoteModel)
                    .filter(
                        QuoteModel.request_uuid == request_uuid,
                        QuoteModel.quote_uuid == quote_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "provider_corp_external_id",
                        "sales_rep_email",
                        "partition_key",
                        "shipping_method",
                        "shipping_amount",
                        "total_quote_amount",
                        "total_quote_discount",
                        "final_total_quote_amount",
                        "currency",
                        "display_currency",
                        "fx_rate",
                        "fx_rate_locked_at",
                        "rounds",
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
        finally:
            Config.db_session.remove()

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> QuoteModel:
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        request_uuid = kwargs.get("request_uuid")

        cols = {
            "request_uuid": request_uuid,
            "partition_key": partition_key,
            "provider_corp_external_id": kwargs.get(
                "provider_corp_external_id", "XXXXXXXXXXXXXXXXXXXX"
            ),
            "shipping_amount": kwargs.get("shipping_amount", 0),
            "total_quote_amount": kwargs.get("total_quote_amount", 0),
            "total_quote_discount": kwargs.get("total_quote_discount", 0),
            "final_total_quote_amount": kwargs.get(
                "final_total_quote_amount", 0
            ),
            "rounds": kwargs.get("rounds", 0),
            "status": kwargs.get("status", "initial"),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "provider_corp_external_id",
            "sales_rep_email",
            "shipping_method",
            "shipping_amount",
            "total_quote_amount",
            "total_quote_discount",
            "final_total_quote_amount",
            "currency",
            "display_currency",
            "fx_rate",
            "fx_rate_locked_at",
            "rounds",
            "notes",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        quote_uuid = kwargs.get("quote_uuid")
        if quote_uuid:
            cols["quote_uuid"] = quote_uuid

        return QuoteModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        request_uuid = kwargs.get("request_uuid")
        quote_uuid = kwargs.get("quote_uuid")

        try:
            # Check for dependent quote_items
            from ...postgresql.quote_item import QuoteItemModel

            dep_count = (
                session.query(QuoteItemModel)
                .filter(
                    QuoteItemModel.quote_uuid == quote_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            row = (
                session.query(QuoteModel)
                .filter(
                    QuoteModel.request_uuid == request_uuid,
                    QuoteModel.quote_uuid == quote_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> QuoteType | None:
        """Convert a SQLAlchemy row to QuoteType."""
        data = normalize_row(row)
        if data is None:
            return None
        return QuoteType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[QuoteType]:
        """Resolve a single quote by request_uuid and quote_uuid."""
        request_uuid = kwargs.get("request_uuid")
        quote_uuid = kwargs.get("quote_uuid")
        if not request_uuid or not quote_uuid:
            return None

        count = self.count(
            request_uuid=request_uuid, quote_uuid=quote_uuid
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(QuoteModel)
            .filter(
                QuoteModel.request_uuid == request_uuid,
                QuoteModel.quote_uuid == quote_uuid,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["QuotePGRepository"]