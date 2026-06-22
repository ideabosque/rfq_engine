# -*- coding: utf-8 -*-
"""DynamoDB repository for ProviderItemBatch entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import provider_item_batches as _provider_item_batches_mod

class ProviderItemBatchRepository(EntityRepository):
    """DynamoDB repository for ProviderItemBatch entity."""

    @property
    def entity_type(self) -> str:
        return "provider_item_batch"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        provider_item_uuid = keys.get("provider_item_uuid")
        batch_no = keys.get("batch_no")
        if not provider_item_uuid or not batch_no:
            return None
        count = _provider_item_batches_mod.get_provider_item_batch_count(
            provider_item_uuid, batch_no
        )
        if count == 0:
            return None
        return _normalize(
            _provider_item_batches_mod.get_provider_item_batch(
                provider_item_uuid, batch_no
            )
        )

    def count(self, **keys: Any) -> int:
        provider_item_uuid = keys.get("provider_item_uuid")
        batch_no = keys.get("batch_no")
        if not provider_item_uuid or not batch_no:
            return 0
        return _provider_item_batches_mod.get_provider_item_batch_count(
            provider_item_uuid, batch_no
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _provider_item_batches_mod.resolve_provider_item_batch_list(
            info, **filters
        )

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _provider_item_batches_mod.insert_update_provider_item_batch(
            info, **kwargs
        )

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _provider_item_batches_mod.delete_provider_item_batch(info, **kwargs)

    def get_type(self, info: Any, batch: Any) -> Any:
        return _provider_item_batches_mod.get_provider_item_batch_type(info, batch)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _provider_item_batches_mod.resolve_provider_item_batch(info, **kwargs)
