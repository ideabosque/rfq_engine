# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for ProviderItems by Item.

Batch loads lists of ProviderItemModel records keyed by (partition_key, item_uuid).
Returns a list of normalized provider_item dicts for each item.
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGProviderItemsByItemLoader(SafeDataLoader):
    """Batch loader returning provider_item lists keyed by (partition_key, item_uuid)."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(PGProviderItemsByItemLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config
        from ..provider_item import ProviderItemModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

        if unique_keys:
            try:
                # Group by partition_key for efficient querying
                pk_groups: Dict[str, List[str]] = {}
                for pk, iu in unique_keys:
                    if pk not in pk_groups:
                        pk_groups[pk] = []
                    pk_groups[pk].append(str(iu) if iu else "")

                for pk, uuids in pk_groups.items():
                    rows = (
                        session.query(ProviderItemModel)
                        .filter(
                            ProviderItemModel.partition_key == pk,
                            ProviderItemModel.item_uuid.in_(
                                [u for u in uuids if u]
                            ),
                        )
                        .all()
                    )
                    for row in rows:
                        key = (row.partition_key, str(row.item_uuid))
                        if key not in key_map:
                            key_map[key] = []
                        key_map[key].append(normalize_row(row))

            except Exception as exc:
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(key, []) for key in keys])


__all__ = ["PGProviderItemsByItemLoader"]