# -*- coding: utf-8 -*-
"""DynamoDB repository for Item entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import item as _item_mod

class ItemRepository(EntityRepository):
    """DynamoDB repository for Item entity."""

    @property
    def entity_type(self) -> str:
        return "item"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        item_uuid = keys.get("item_uuid")
        if not partition_key or not item_uuid:
            return None
        count = _item_mod.get_item_count(partition_key, item_uuid)
        if count == 0:
            return None
        return _normalize(_item_mod.get_item(partition_key, item_uuid))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        item_uuid = keys.get("item_uuid")
        if not partition_key or not item_uuid:
            return 0
        return _item_mod.get_item_count(partition_key, item_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _item_mod.resolve_item_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _item_mod.insert_update_item(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _item_mod.delete_item(info, **kwargs)

    def get_type(self, info: Any, item: Any) -> Any:
        """Return ItemType from a PynamoDB model instance."""
        return _item_mod.get_item_type(info, item)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        """Resolve a single item (supports item_external_id lookup)."""
        return _item_mod.resolve_item(info, **kwargs)
