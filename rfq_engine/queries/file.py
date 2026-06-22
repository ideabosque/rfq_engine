#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo
from silvaengine_utility import method_cache

from ..handlers.config import Config
from ..models.repositories import get_repo
from ..types.file import FileListType, FileType


def resolve_file(info: ResolveInfo, **kwargs: Dict[str, Any]) -> FileType | None:
    return get_repo("file").resolve_single(info, **kwargs)


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("queries", "file"),
    cache_enabled=Config.is_cache_enabled,
)
def resolve_file_list(info: ResolveInfo, **kwargs: Dict[str, Any]) -> FileListType:
    return get_repo("file").list(info, **kwargs)
