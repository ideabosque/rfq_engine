# -*- coding: utf-8 -*-
"""PostgreSQL repository for AvailabilityHold entity.

AvailabilityHold uses backend-specific atomic transaction semantics
(SELECT...FOR UPDATE pattern for PostgreSQL) and is not managed via
standard CRUD repositories. The acquire/release/confirm/expire
mutations are handled by dedicated availability handlers.

This repository implements get/count for lookups but raises
NotImplementedError for list/insert_update/delete, mirroring the
DynamoDB wrapper behavior.
"""
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict, Optional

from graphene import ResolveInfo

from ....handlers.config import Config
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.availability_hold import AvailabilityHoldModel


class AvailabilityHoldPGRepository(EntityRepository):
    """PostgreSQL repository for AvailabilityHold entity.

    Only get/count are implemented here. The acquire/release/confirm/expire
    lifecycle is handled by dedicated availability handlers that use
    SELECT...FOR UPDATE atomic transactions.
    """

    @property
    def entity_type(self) -> str:
        return "availability_hold"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        hold_token = keys.get("hold_token")
        if not partition_key or not hold_token:
            return None
        session = Config.db_session
        row = (
            session.query(AvailabilityHoldModel)
            .filter(
                AvailabilityHoldModel.partition_key == partition_key,
                AvailabilityHoldModel.hold_token == hold_token,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        hold_token = keys.get("hold_token")
        if not partition_key or not hold_token:
            return 0
        session = Config.db_session
        return (
            session.query(AvailabilityHoldModel)
            .filter(
                AvailabilityHoldModel.partition_key == partition_key,
                AvailabilityHoldModel.hold_token == hold_token,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Not implemented — availability holds use acquire/release/confirm/expire mutations."""
        raise NotImplementedError(
            "AvailabilityHold.list is not supported. "
            "Use the acquire/release/confirm/expire availability handlers instead."
        )

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Not implemented — availability holds use atomic transaction semantics."""
        raise NotImplementedError(
            "AvailabilityHold.insert_update is not supported. "
            "Use the acquire/release/confirm/expire availability handlers instead."
        )

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        """Not implemented — availability holds use release/expire mutations."""
        raise NotImplementedError(
            "AvailabilityHold.delete is not supported. "
            "Use the release/expire availability handlers instead."
        )

    def get_type(self, info: ResolveInfo, row: Any) -> Any:
        """Convert a SQLAlchemy row to a dict for availability handlers."""
        return normalize_row(row)

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[Any]:
        """Resolve a single availability hold by partition_key and hold_token."""
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        hold_token = kwargs.get("hold_token")
        if not partition_key or not hold_token:
            return None

        count = self.count(
            partition_key=partition_key, hold_token=hold_token
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(AvailabilityHoldModel)
            .filter(
                AvailabilityHoldModel.partition_key == partition_key,
                AvailabilityHoldModel.hold_token == hold_token,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["AvailabilityHoldPGRepository"]