# -*- coding: utf-8 -*-
"""DynamoDB repository for FxRate entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import fx_rate as _fx_rate_mod

class FxRateRepository(EntityRepository):
    """DynamoDB repository for FxRate entity."""

    @property
    def entity_type(self) -> str:
        return "fx_rate"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        fx_rate_uuid = keys.get("fx_rate_uuid")
        if not partition_key or not fx_rate_uuid:
            return None
        count = _fx_rate_mod.get_fx_rate_count(partition_key, fx_rate_uuid)
        if count == 0:
            return None
        return _normalize(_fx_rate_mod.get_fx_rate(partition_key, fx_rate_uuid))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        fx_rate_uuid = keys.get("fx_rate_uuid")
        if not partition_key or not fx_rate_uuid:
            return 0
        return _fx_rate_mod.get_fx_rate_count(partition_key, fx_rate_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _fx_rate_mod.resolve_fx_rate_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _fx_rate_mod.insert_update_fx_rate(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _fx_rate_mod.delete_fx_rate(info, **kwargs)

    def get_type(self, info: Any, fx_rate: Any) -> Any:
        return _fx_rate_mod.get_fx_rate_type(info, fx_rate)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _fx_rate_mod.resolve_fx_rate(info, **kwargs)
