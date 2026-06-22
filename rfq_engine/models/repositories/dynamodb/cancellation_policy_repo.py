# -*- coding: utf-8 -*-
"""DynamoDB repository for CancellationPolicy entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import cancellation_policy as _cancellation_policy_mod

class CancellationPolicyRepository(EntityRepository):
    """DynamoDB repository for CancellationPolicy entity."""

    @property
    def entity_type(self) -> str:
        return "cancellation_policy"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        policy_uuid = keys.get("policy_uuid")
        if not partition_key or not policy_uuid:
            return None
        count = _cancellation_policy_mod.get_cancellation_policy_count(
            partition_key, policy_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _cancellation_policy_mod.get_cancellation_policy(
                partition_key, policy_uuid
            )
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        policy_uuid = keys.get("policy_uuid")
        if not partition_key or not policy_uuid:
            return 0
        return _cancellation_policy_mod.get_cancellation_policy_count(
            partition_key, policy_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _cancellation_policy_mod.resolve_cancellation_policy_list(
            info, **filters
        )

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _cancellation_policy_mod.insert_update_cancellation_policy(
            info, **kwargs
        )

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _cancellation_policy_mod.delete_cancellation_policy(info, **kwargs)

    def get_type(self, info: Any, policy: Any) -> Any:
        return _cancellation_policy_mod.get_cancellation_policy_type(info, policy)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _cancellation_policy_mod.resolve_cancellation_policy(info, **kwargs)
