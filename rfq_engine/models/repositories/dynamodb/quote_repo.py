# -*- coding: utf-8 -*-
"""DynamoDB repository for Quote entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import quote as _quote_mod

class QuoteRepository(EntityRepository):
    """DynamoDB repository for Quote entity."""

    @property
    def entity_type(self) -> str:
        return "quote"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        request_uuid = keys.get("request_uuid")
        quote_uuid = keys.get("quote_uuid")
        if not request_uuid or not quote_uuid:
            return None
        count = _quote_mod.get_quote_count(request_uuid, quote_uuid)
        if count == 0:
            return None
        return _normalize(_quote_mod.get_quote(request_uuid, quote_uuid))

    def count(self, **keys: Any) -> int:
        request_uuid = keys.get("request_uuid")
        quote_uuid = keys.get("quote_uuid")
        if not request_uuid or not quote_uuid:
            return 0
        return _quote_mod.get_quote_count(request_uuid, quote_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _quote_mod.resolve_quote_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _quote_mod.insert_update_quote(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _quote_mod.delete_quote(info, **kwargs)

    def get_type(self, info: Any, quote: Any) -> Any:
        return _quote_mod.get_quote_type(info, quote)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _quote_mod.resolve_quote(info, **kwargs)
