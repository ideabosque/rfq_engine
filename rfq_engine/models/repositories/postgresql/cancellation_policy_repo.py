# -*- coding: utf-8 -*-
"""PostgreSQL repository for CancellationPolicy entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL CancellationPolicyModel.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.cancellation_policy import (
    CancellationPolicyListType,
    CancellationPolicyType,
)
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.cancellation_policy import CancellationPolicyModel


class CancellationPolicyPGRepository(EntityRepository):
    """PostgreSQL repository for CancellationPolicy entity."""

    @property
    def entity_type(self) -> str:
        return "cancellation_policy"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        policy_uuid = keys.get("policy_uuid")
        if not partition_key or not policy_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(CancellationPolicyModel)
            .filter(
                CancellationPolicyModel.partition_key == partition_key,
                CancellationPolicyModel.policy_uuid == policy_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        policy_uuid = keys.get("policy_uuid")
        if not partition_key or not policy_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(CancellationPolicyModel)
            .filter(
                CancellationPolicyModel.partition_key == partition_key,
                CancellationPolicyModel.policy_uuid == policy_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated cancellation_policy list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        provider_item_uuid = filters.get("provider_item_uuid")
        status = filters.get("status")

        query = session.query(CancellationPolicyModel)
        if partition_key:
            query = query.filter(CancellationPolicyModel.partition_key == partition_key)
        if provider_item_uuid:
            query = query.filter(CancellationPolicyModel.provider_item_uuid == provider_item_uuid)
        if status:
            query = query.filter(CancellationPolicyModel.status == status)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(CancellationPolicyModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        policy_list = [self.get_type(info, row) for row in rows]
        return CancellationPolicyListType(cancellation_policy_list=policy_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        policy_uuid = kwargs.get("policy_uuid")

        try:
            if policy_uuid:
                # Update existing
                row = (
                    session.query(CancellationPolicyModel)
                    .filter(
                        CancellationPolicyModel.partition_key == partition_key,
                        CancellationPolicyModel.policy_uuid == policy_uuid,
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
                        "provider_item_uuid",
                        "label",
                        "description",
                        "tiers",
                        "notes_template_uuid",
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

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> CancellationPolicyModel:
        partition_key = info.context.get("partition_key")
        policy_uuid = kwargs.get("policy_uuid")

        cols = {
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "provider_item_uuid",
            "label",
            "description",
            "tiers",
            "notes_template_uuid",
            "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        if policy_uuid:
            cols["policy_uuid"] = policy_uuid

        return CancellationPolicyModel(**cols)

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key")
        policy_uuid = kwargs.get("policy_uuid")

        try:
            # No child dependencies for CancellationPolicy
            row = (
                session.query(CancellationPolicyModel)
                .filter(
                    CancellationPolicyModel.partition_key == partition_key,
                    CancellationPolicyModel.policy_uuid == policy_uuid,
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

    def get_type(self, info: ResolveInfo, row: Any) -> CancellationPolicyType:
        """Convert a SQLAlchemy row to CancellationPolicyType."""
        data = normalize_row(row)
        if data is None:
            return None
        return CancellationPolicyType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[CancellationPolicyType]:
        """Resolve a single cancellation_policy by policy_uuid."""
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        if "policy_uuid" not in kwargs:
            return None

        count = self.count(
            partition_key=partition_key, policy_uuid=kwargs["policy_uuid"]
        )
        if count == 0:
            return None

        row = (
            session.query(CancellationPolicyModel)
            .filter(
                CancellationPolicyModel.partition_key == partition_key,
                CancellationPolicyModel.policy_uuid == kwargs["policy_uuid"],
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["CancellationPolicyPGRepository"]