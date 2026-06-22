# -*- coding: utf-8 -*-
"""DynamoDB repository for Bundle entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import bundle as _bundle_mod

class BundleRepository(EntityRepository):
    """DynamoDB repository for Bundle entity."""

    @property
    def entity_type(self) -> str:
        return "bundle"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        bundle_uuid = keys.get("bundle_uuid")
        if not partition_key or not bundle_uuid:
            return None
        count = _bundle_mod.get_bundle_count(partition_key, bundle_uuid)
        if count == 0:
            return None
        return _normalize(_bundle_mod.get_bundle(partition_key, bundle_uuid))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        bundle_uuid = keys.get("bundle_uuid")
        if not partition_key or not bundle_uuid:
            return 0
        return _bundle_mod.get_bundle_count(partition_key, bundle_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _bundle_mod.resolve_bundle_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _bundle_mod.insert_update_bundle(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _bundle_mod.delete_bundle(info, **kwargs)

    def get_type(self, info: Any, bundle: Any) -> Any:
        return _bundle_mod.get_bundle_type(info, bundle)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _bundle_mod.resolve_bundle(info, **kwargs)
