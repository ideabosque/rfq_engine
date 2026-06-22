# -*- coding: utf-8 -*-
"""PostgreSQL repository for DiscountPrompt entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL DiscountPromptModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.discount_prompt import DiscountPromptListType, DiscountPromptType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.discount_prompt import DiscountPromptModel


class DiscountPromptPGRepository(EntityRepository):
    """PostgreSQL repository for DiscountPrompt entity."""

    @property
    def entity_type(self) -> str:
        return "discount_prompt"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        discount_prompt_uuid = keys.get("discount_prompt_uuid")
        if not partition_key or not discount_prompt_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(DiscountPromptModel)
            .filter(
                DiscountPromptModel.partition_key == partition_key,
                DiscountPromptModel.discount_prompt_uuid == discount_prompt_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        discount_prompt_uuid = keys.get("discount_prompt_uuid")
        if not partition_key or not discount_prompt_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(DiscountPromptModel)
            .filter(
                DiscountPromptModel.partition_key == partition_key,
                DiscountPromptModel.discount_prompt_uuid == discount_prompt_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated discount prompt list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        scope = filters.get("scope")
        tags = filters.get("tags")
        status = filters.get("status")

        query = session.query(DiscountPromptModel)
        if partition_key:
            query = query.filter(
                DiscountPromptModel.partition_key == partition_key
            )
        if scope:
            query = query.filter(DiscountPromptModel.scope == scope)
        if status:
            query = query.filter(DiscountPromptModel.status == status)
        if tags:
            # tags is a JSONB array; filter for prompts containing any of the tags
            for tag in tags:
                query = query.filter(
                    DiscountPromptModel.tags.contains(tag)
                )

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(DiscountPromptModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        prompt_list = [self.get_type(info, row) for row in rows]
        return DiscountPromptListType(
            discount_prompt_list=prompt_list, total=total
        )

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        discount_prompt_uuid = kwargs.get("discount_prompt_uuid")

        try:
            if discount_prompt_uuid:
                # Update existing
                row = (
                    session.query(DiscountPromptModel)
                    .filter(
                        DiscountPromptModel.partition_key == partition_key,
                        DiscountPromptModel.discount_prompt_uuid == discount_prompt_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "scope",
                        "tags",
                        "discount_prompt",
                        "conditions",
                        "discount_rules",
                        "priority",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> DiscountPromptModel:
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")

        cols = {
            "partition_key": partition_key,
            "conditions": kwargs.get("conditions", []),
            "discount_rules": kwargs.get("discount_rules", []),
            "status": kwargs.get("status", "in_review"),
            "priority": kwargs.get("priority", 0),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "scope",
            "tags",
            "discount_prompt",
            "conditions",
            "discount_rules",
            "priority",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        discount_prompt_uuid = kwargs.get("discount_prompt_uuid")
        if discount_prompt_uuid:
            cols["discount_prompt_uuid"] = discount_prompt_uuid

        return DiscountPromptModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        discount_prompt_uuid = kwargs.get("discount_prompt_uuid")

        try:
            # No child dependencies for discount prompts
            row = (
                session.query(DiscountPromptModel)
                .filter(
                    DiscountPromptModel.partition_key == partition_key,
                    DiscountPromptModel.discount_prompt_uuid == discount_prompt_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> DiscountPromptType:
        """Convert a SQLAlchemy row to DiscountPromptType."""
        data = normalize_row(row)
        if data is None:
            return None
        return DiscountPromptType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[DiscountPromptType]:
        """Resolve a single discount prompt by partition_key and discount_prompt_uuid."""
        partition_key = info.context.get("partition_key")
        discount_prompt_uuid = kwargs.get("discount_prompt_uuid")
        if not discount_prompt_uuid:
            return None

        count = self.count(
            partition_key=partition_key,
            discount_prompt_uuid=discount_prompt_uuid,
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(DiscountPromptModel)
            .filter(
                DiscountPromptModel.partition_key == partition_key,
                DiscountPromptModel.discount_prompt_uuid == discount_prompt_uuid,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["DiscountPromptPGRepository"]