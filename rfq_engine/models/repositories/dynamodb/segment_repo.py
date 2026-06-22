# -*- coding: utf-8 -*-
"""DynamoDB repository for Segment entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import segment as _segment_mod

class SegmentRepository(EntityRepository):
    """DynamoDB repository for Segment entity."""

    @property
    def entity_type(self) -> str:
        return "segment"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        segment_uuid = keys.get("segment_uuid")
        if not partition_key or not segment_uuid:
            return None
        count = _segment_mod.get_segment_count(partition_key, segment_uuid)
        if count == 0:
            return None
        return _normalize(_segment_mod.get_segment(partition_key, segment_uuid))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        segment_uuid = keys.get("segment_uuid")
        if not partition_key or not segment_uuid:
            return 0
        return _segment_mod.get_segment_count(partition_key, segment_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _segment_mod.resolve_segment_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _segment_mod.insert_update_segment(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _segment_mod.delete_segment(info, **kwargs)

    def get_type(self, info: Any, segment: Any) -> Any:
        return _segment_mod.get_segment_type(info, segment)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _segment_mod.resolve_segment(info, **kwargs)
