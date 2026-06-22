# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo
from silvaengine_utility import method_cache

from ..handlers.config import Config
from ..models.repositories import get_repo
from ..types.cancellation_policy import (
    CancellationPolicyListType,
    CancellationPolicyType,
)


def resolve_cancellation_policy(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> CancellationPolicyType | None:
    return get_repo("cancellation_policy").resolve_single(info, **kwargs)


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("queries", "cancellation_policy"),
    cache_enabled=Config.is_cache_enabled,
)
def resolve_cancellation_policy_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> CancellationPolicyListType:
    return get_repo("cancellation_policy").list(info, **kwargs)