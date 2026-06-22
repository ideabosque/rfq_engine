# -*- coding: utf-8 -*-
"""DynamoDB repository for QuoteItem entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import quote_item as _quote_item_mod

class QuoteItemRepository(EntityRepository):
    """DynamoDB repository for QuoteItem entity."""

    @property
    def entity_type(self) -> str:
        return "quote_item"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        quote_uuid = keys.get("quote_uuid")
        quote_item_uuid = keys.get("quote_item_uuid")
        if not quote_uuid or not quote_item_uuid:
            return None
        count = _quote_item_mod.get_quote_item_count(quote_uuid, quote_item_uuid)
        if count == 0:
            return None
        return _normalize(
            _quote_item_mod.get_quote_item(quote_uuid, quote_item_uuid)
        )

    def count(self, **keys: Any) -> int:
        quote_uuid = keys.get("quote_uuid")
        quote_item_uuid = keys.get("quote_item_uuid")
        if not quote_uuid or not quote_item_uuid:
            return 0
        return _quote_item_mod.get_quote_item_count(quote_uuid, quote_item_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _quote_item_mod.resolve_quote_item_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _quote_item_mod.insert_update_quote_item(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _quote_item_mod.delete_quote_item(info, **kwargs)

    def get_type(self, info: Any, quote_item: Any) -> Any:
        return _quote_item_mod.get_quote_item_type(info, quote_item)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _quote_item_mod.resolve_quote_item(info, **kwargs)
