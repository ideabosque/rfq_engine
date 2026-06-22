#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List

from graphene import ResolveInfo
from silvaengine_utility import method_cache

from ..handlers.config import Config
from ..models.repositories import get_loaders, get_repo
from ..models.repositories.utils import combine_all_item_price_tiers
from ..types.item_price_tier import ItemPriceTierListType, ItemPriceTierType


def resolve_item_price_tier(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> ItemPriceTierType | None:
    return get_repo("item_price_tier").resolve_single(info, **kwargs)


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("queries", "item_price_tier"),
    cache_enabled=Config.is_cache_enabled,
)
def resolve_item_price_tier_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> ItemPriceTierListType:
    return get_repo("item_price_tier").list(info, **kwargs)


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("queries", "item_price_tier"),
    cache_enabled=Config.is_cache_enabled,
)
def resolve_item_price_tiers(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> List[ItemPriceTierType]:
    """
    Resolve item price tiers for quote items using batch loaders.

    Uses the backend-dispatched ``combine_all_item_price_tiers`` helper to
    handle the Promise chaining and hierarchical loading logic, then
    converts the results to ``ItemPriceTierType``. Both backends yield
    normalized dicts at this point (DynamoDB loaders call ``normalize_model``
    before yielding; PostgreSQL loaders yield row dicts directly), so a
    single ``normalize_to_json`` path covers both.

    Args:
        info: GraphQL resolve info
        kwargs: Must contain 'email' and optionally 'quote_items'

    Returns:
        Promise that resolves to list of ItemPriceTierType objects with price tier information
    """
    from ..utils.normalization import normalize_to_json

    loaders = get_loaders(info.context)
    partition_key = info.context.get("partition_key")
    email = kwargs.get("email")
    quote_items = kwargs.get("quote_items", [])

    def convert_to_types(tier_models):
        """Convert normalized tier dicts to ``ItemPriceTierType``.

        ``normalize_to_json`` also tolerates a stray PynamoDB model instance
        (via its ``attribute_values`` branch), so this stays backend-agnostic
        even if a cached model ever surfaces.
        """
        return [
            ItemPriceTierType(**normalize_to_json(tier_model))
            for tier_model in tier_models
        ]

    return combine_all_item_price_tiers(
        partition_key, email, quote_items, loaders
    ).then(convert_to_types)
