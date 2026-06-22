# -*- coding: utf-8 -*-
"""DynamoDB repository for File entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, Optional

from ...repositories.base import EntityRepository
from ._base import _normalize

from ...dynamodb import file as _file_mod

class FileRepository(EntityRepository):
    """DynamoDB repository for File entity."""

    @property
    def entity_type(self) -> str:
        return "file"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        request_uuid = keys.get("request_uuid")
        file_name = keys.get("file_name")
        if not request_uuid or not file_name:
            return None
        count = _file_mod.get_file_count(request_uuid, file_name)
        if count == 0:
            return None
        return _normalize(_file_mod.get_file(request_uuid, file_name))

    def count(self, **keys: Any) -> int:
        request_uuid = keys.get("request_uuid")
        file_name = keys.get("file_name")
        if not request_uuid or not file_name:
            return 0
        return _file_mod.get_file_count(request_uuid, file_name)

    def list(self, info: Any, **filters: Any) -> Any:
        return _file_mod.resolve_file_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _file_mod.insert_update_file(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _file_mod.delete_file(info, **kwargs)

    def get_type(self, info: Any, file: Any) -> Any:
        return _file_mod.get_file_type(info, file)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _file_mod.resolve_file(info, **kwargs)
