# -*- coding: utf-8 -*-
"""DynamoDB repository for ItemCatalogRef entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import item_catalog_ref as _item_catalog_ref_mod

class ItemCatalogRefRepository(EntityRepository):
    """DynamoDB repository for ItemCatalogRef entity."""

    @property
    def entity_type(self) -> str:
        return "item_catalog_ref"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        catalog_ref_uuid = keys.get("catalog_ref_uuid")
        if not partition_key or not catalog_ref_uuid:
            return None
        count = _item_catalog_ref_mod.get_item_catalog_ref_count(
            partition_key, catalog_ref_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _item_catalog_ref_mod.get_item_catalog_ref(
                partition_key, catalog_ref_uuid
            )
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        catalog_ref_uuid = keys.get("catalog_ref_uuid")
        if not partition_key or not catalog_ref_uuid:
            return 0
        return _item_catalog_ref_mod.get_item_catalog_ref_count(
            partition_key, catalog_ref_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _item_catalog_ref_mod.resolve_item_catalog_ref_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _item_catalog_ref_mod.insert_update_item_catalog_ref(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _item_catalog_ref_mod.delete_item_catalog_ref(info, **kwargs)

    def get_type(self, info: Any, catalog_ref: Any) -> Any:
        return _item_catalog_ref_mod.get_item_catalog_ref_type(info, catalog_ref)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _item_catalog_ref_mod.resolve_item_catalog_ref(info, **kwargs)

    def find_refs(self, info: Any, **kwargs: Any) -> Any:
        return _item_catalog_ref_mod.find_item_catalog_refs(info, **kwargs)
