# -*- coding: utf-8 -*-
"""Backend-dispatched combination helpers.

``combine_all_discount_prompts`` and ``combine_all_item_price_tiers`` route to
the active backend's implementation based on ``Config.DB_BACKEND``. Both
helpers receive a ``loaders`` instance returned by ``get_loaders(context)``
and use only loader properties whose names match across
``RequestLoaders`` (DynamoDB) and ``PGRequestLoaders`` (PostgreSQL).
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List

from ...handlers.config import Config


def combine_all_discount_prompts(
    partition_key: str,
    email: str,
    quote_items: List[Dict[str, Any]],
    loaders: Any,
) -> Any:
    """Dispatch to the active backend's discount-prompt combination helper."""
    if Config.DB_BACKEND == "postgresql":
        from ..postgresql.utils import combine_all_discount_prompts as _combine

        return _combine(partition_key, email, quote_items, loaders)
    from ..dynamodb.utils import combine_all_discount_prompts as _combine

    return _combine(partition_key, email, quote_items, loaders)


def combine_all_item_price_tiers(
    partition_key: str,
    email: str,
    quote_items: List[Dict[str, Any]],
    loaders: Any,
) -> Any:
    """Dispatch to the active backend's price-tier combination helper."""
    if Config.DB_BACKEND == "postgresql":
        from ..postgresql.utils import combine_all_item_price_tiers as _combine

        return _combine(partition_key, email, quote_items, loaders)
    from ..dynamodb.utils import combine_all_item_price_tiers as _combine

    return _combine(partition_key, email, quote_items, loaders)


__all__ = [
    "combine_all_discount_prompts",
    "combine_all_item_price_tiers",
]