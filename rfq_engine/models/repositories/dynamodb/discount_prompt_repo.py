# -*- coding: utf-8 -*-
"""DynamoDB repository for DiscountPrompt entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import discount_prompt as _discount_prompt_mod

class DiscountPromptRepository(EntityRepository):
    """DynamoDB repository for DiscountPrompt entity."""

    @property
    def entity_type(self) -> str:
        return "discount_prompt"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        discount_prompt_uuid = keys.get("discount_prompt_uuid")
        if not partition_key or not discount_prompt_uuid:
            return None
        count = _discount_prompt_mod.get_discount_prompt_count(
            partition_key, discount_prompt_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _discount_prompt_mod.get_discount_prompt(
                partition_key, discount_prompt_uuid
            )
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        discount_prompt_uuid = keys.get("discount_prompt_uuid")
        if not partition_key or not discount_prompt_uuid:
            return 0
        return _discount_prompt_mod.get_discount_prompt_count(
            partition_key, discount_prompt_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        return _discount_prompt_mod.resolve_discount_prompt_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _discount_prompt_mod.insert_update_discount_prompt(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _discount_prompt_mod.delete_discount_prompt(info, **kwargs)

    def get_type(self, info: Any, prompt: Any) -> Any:
        return _discount_prompt_mod.get_discount_prompt_type(info, prompt)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _discount_prompt_mod.resolve_discount_prompt(info, **kwargs)
