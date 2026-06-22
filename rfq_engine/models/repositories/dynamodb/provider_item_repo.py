# -*- coding: utf-8 -*-
"""DynamoDB repository for ProviderItem entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import provider_item as _provider_item_mod

class ProviderItemRepository(EntityRepository):
    """DynamoDB repository for ProviderItem entity."""

    @property
    def entity_type(self) -> str:
        return "provider_item"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        provider_item_uuid = keys.get("provider_item_uuid")
        if not partition_key or not provider_item_uuid:
            return None
        count = _provider_item_mod.get_provider_item_count(
            partition_key, provider_item_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _provider_item_mod.get_provider_item(partition_key, provider_item_uuid)
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        provider_item_uuid = keys.get("provider_item_uuid")
        if not partition_key or not provider_item_uuid:
            return 0
        return _provider_item_mod.get_provider_item_count(
            partition_key, provider_item_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _provider_item_mod.resolve_provider_item_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _provider_item_mod.insert_update_provider_item(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _provider_item_mod.delete_provider_item(info, **kwargs)

    def get_type(self, info: Any, provider_item: Any) -> Any:
        return _provider_item_mod.get_provider_item_type(info, provider_item)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _provider_item_mod.resolve_provider_item(info, **kwargs)
