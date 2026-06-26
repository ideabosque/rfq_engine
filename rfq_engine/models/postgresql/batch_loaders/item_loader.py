# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for Item entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGItemLoader(SafeDataLoader):
    """Batch loader for ItemModel records keyed by (partition_key, item_uuid)."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(PGItemLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config
        from ..item import ItemModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        if unique_keys:
            try:
                # Build a list of (partition_key, item_uuid) pairs to query
                # SQLAlchemy doesn't support composite IN directly, so we
                # query by partition_key groups
                pk_groups: Dict[str, List[str]] = {}
                for pk, iu in unique_keys:
                    if pk not in pk_groups:
                        pk_groups[pk] = []
                    pk_groups[pk].append(str(iu) if iu else "")

                for pk, uuids in pk_groups.items():
                    rows = (
                        session.query(ItemModel)
                        .filter(
                            ItemModel.partition_key == pk,
                            ItemModel.item_uuid.in_([u for u in uuids if u]),
                        )
                        .all()
                    )
                    for row in rows:
                        key = (row.partition_key, str(row.item_uuid))
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


__all__ = ["PGItemLoader"]