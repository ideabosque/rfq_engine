# -*- coding: utf-8 -*-
"""DynamoDB repository for AvailabilityHold entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize


class AvailabilityHoldRepository(EntityRepository):
    """DynamoDB repository for AvailabilityHold entity."""

    @property
    def entity_type(self) -> str:
        return "availability_hold"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        hold_token = keys.get("hold_token")
        if not partition_key or not hold_token:
            return None
        from ...availability_hold import (
            get_availability_hold,
            get_availability_hold_count,
        )

        count = get_availability_hold_count(partition_key, hold_token)
        if count == 0:
            return None
        return _normalize(get_availability_hold(partition_key, hold_token))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        hold_token = keys.get("hold_token")
        if not partition_key or not hold_token:
            return 0
        from ...dynamodb.availability_hold import get_availability_hold_count

        return get_availability_hold_count(partition_key, hold_token)

    def list(self, info: Any, **filters: Any) -> Any:
        # AvailabilityHold does not have a standard list resolver
        raise NotImplementedError(
            "AvailabilityHold list is handled by check_availability query"
        )

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        raise NotImplementedError(
            "AvailabilityHold uses acquire/release/confirm/expire mutations"
        )

    def delete(self, info: Any, **kwargs: Any) -> bool:
        raise NotImplementedError(
            "AvailabilityHold uses release mutation"
        )
