# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo
from silvaengine_utility import method_cache

from ..handlers.config import Config
from ..models.repositories import get_repo
from ..types.fx_rate import FxRateListType, FxRateType


def resolve_fx_rate(info: ResolveInfo, **kwargs: Dict[str, Any]) -> FxRateType | None:
    return get_repo("fx_rate").resolve_single(info, **kwargs)


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("queries", "fx_rate"),
    cache_enabled=Config.is_cache_enabled,
)
def resolve_fx_rate_list(info: ResolveInfo, **kwargs: Dict[str, Any]) -> FxRateListType:
    return get_repo("fx_rate").list(info, **kwargs)