# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for Segment entity.

Batch loads SegmentModel records keyed by (partition_key, segment_uuid).
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGSegmentLoader(SafeDataLoader):
    """Batch loader for SegmentModel keyed by (partition_key, segment_uuid)."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(PGSegmentLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config
        from ..segment import SegmentModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        if unique_keys:
            try:
                # Group by partition_key for efficient querying
                pk_groups: Dict[str, List[str]] = {}
                for pk, su in unique_keys:
                    if pk not in pk_groups:
                        pk_groups[pk] = []
                    pk_groups[pk].append(str(su) if su else "")

                for pk, uuids in pk_groups.items():
                    rows = (
                        session.query(SegmentModel)
                        .filter(
                            SegmentModel.partition_key == pk,
                            SegmentModel.segment_uuid.in_(
                                [u for u in uuids if u]
                            ),
                        )
                        .all()
                    )
                    for row in rows:
                        key = (row.partition_key, str(row.segment_uuid))
                        key_map[key] = normalize_row(row)

            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(key) for key in keys])


__all__ = ["PGSegmentLoader"]