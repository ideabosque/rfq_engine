# -*- coding: utf-8 -*-
"""DynamoDB repository for SegmentContact entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import segment_contact as _segment_contact_mod

class SegmentContactRepository(EntityRepository):
    """DynamoDB repository for SegmentContact entity."""

    @property
    def entity_type(self) -> str:
        return "segment_contact"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        email = keys.get("email")
        if not partition_key or not email:
            return None
        count = _segment_contact_mod.get_segment_contact_count(
            partition_key, email
        )
        if count == 0:
            return None
        return _normalize(
            _segment_contact_mod.get_segment_contact(partition_key, email)
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        email = keys.get("email")
        if not partition_key or not email:
            return 0
        return _segment_contact_mod.get_segment_contact_count(partition_key, email)

    def list(self, info: Any, **filters: Any) -> Any:
        return _segment_contact_mod.resolve_segment_contact_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _segment_contact_mod.insert_update_segment_contact(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _segment_contact_mod.delete_segment_contact(info, **kwargs)

    def get_type(self, info: Any, contact: Any) -> Any:
        return _segment_contact_mod.get_segment_contact_type(info, contact)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _segment_contact_mod.resolve_segment_contact(info, **kwargs)
