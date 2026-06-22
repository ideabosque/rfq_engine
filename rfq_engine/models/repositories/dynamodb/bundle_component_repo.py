# -*- coding: utf-8 -*-
"""DynamoDB repository for BundleComponent entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import bundle_component as _bundle_component_mod

class BundleComponentRepository(EntityRepository):
    """DynamoDB repository for BundleComponent entity."""

    @property
    def entity_type(self) -> str:
        return "bundle_component"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        bundle_component_uuid = keys.get("bundle_component_uuid")
        if not partition_key or not bundle_component_uuid:
            return None
        count = _bundle_component_mod.get_bundle_component_count(
            partition_key, bundle_component_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _bundle_component_mod.get_bundle_component(
                partition_key, bundle_component_uuid
            )
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        bundle_component_uuid = keys.get("bundle_component_uuid")
        if not partition_key or not bundle_component_uuid:
            return 0
        return _bundle_component_mod.get_bundle_component_count(
            partition_key, bundle_component_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _bundle_component_mod.resolve_bundle_component_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _bundle_component_mod.insert_update_bundle_component(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _bundle_component_mod.delete_bundle_component(info, **kwargs)

    def get_type(self, info: Any, component: Any) -> Any:
        return _bundle_component_mod.get_bundle_component_type(info, component)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _bundle_component_mod.resolve_bundle_component(info, **kwargs)
