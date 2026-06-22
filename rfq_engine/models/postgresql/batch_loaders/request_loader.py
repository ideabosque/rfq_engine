# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for Request entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGRequestLoader(SafeDataLoader):
    """Batch loader for RequestModel records keyed by (partition_key, request_uuid)."""

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config
        from ..request import RequestModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        if unique_keys:
            try:
                pk_groups: Dict[str, List[str]] = {}
                for partition_key, request_uuid in unique_keys:
                    pk_groups.setdefault(partition_key, []).append(str(request_uuid))

                for partition_key, request_uuids in pk_groups.items():
                    rows = (
                        session.query(RequestModel)
                        .filter(
                            RequestModel.partition_key == partition_key,
                            RequestModel.request_uuid.in_([u for u in request_uuids if u]),
                        )
                        .all()
                    )
                    for row in rows:
                        key_map[(row.partition_key, str(row.request_uuid))] = normalize_row(row)
            except Exception as exc:
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get((key[0], str(key[1]))) for key in keys])


__all__ = ["PGRequestLoader"]