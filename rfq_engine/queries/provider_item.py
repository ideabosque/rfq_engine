#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo
from silvaengine_utility import method_cache

from ..handlers.config import Config
from ..models.repositories import get_repo
from ..types.provider_item import ProviderItemListType, ProviderItemType


def resolve_provider_item(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> ProviderItemType | None:
    return get_repo("provider_item").resolve_single(info, **kwargs)


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("queries", "provider_item"),
    cache_enabled=Config.is_cache_enabled,
)
def resolve_provider_item_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> ProviderItemListType:
    return get_repo("provider_item").list(info, **kwargs)
