# -*- coding: utf-8 -*-
"""DynamoDB repository for ItemPriceTier entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import item_price_tier as _item_price_tier_mod

class ItemPriceTierRepository(EntityRepository):
    """DynamoDB repository for ItemPriceTier entity."""

    @property
    def entity_type(self) -> str:
        return "item_price_tier"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        item_uuid = keys.get("item_uuid")
        item_price_tier_uuid = keys.get("item_price_tier_uuid")
        if not item_uuid or not item_price_tier_uuid:
            return None
        count = _item_price_tier_mod.get_item_price_tier_count(
            item_uuid, item_price_tier_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _item_price_tier_mod.get_item_price_tier(
                item_uuid, item_price_tier_uuid
            )
        )

    def count(self, **keys: Any) -> int:
        item_uuid = keys.get("item_uuid")
        item_price_tier_uuid = keys.get("item_price_tier_uuid")
        if not item_uuid or not item_price_tier_uuid:
            return 0
        return _item_price_tier_mod.get_item_price_tier_count(
            item_uuid, item_price_tier_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _item_price_tier_mod.resolve_item_price_tier_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _item_price_tier_mod.insert_update_item_price_tier(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _item_price_tier_mod.delete_item_price_tier(info, **kwargs)

    def get_type(self, info: Any, tier: Any) -> Any:
        return _item_price_tier_mod.get_item_price_tier_type(info, tier)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _item_price_tier_mod.resolve_item_price_tier(info, **kwargs)
