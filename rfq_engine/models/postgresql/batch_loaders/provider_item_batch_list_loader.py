# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for ProviderItemBatch lists by provider_item.

Batch loads lists of ProviderItemBatchModel records keyed by provider_item_uuid.
Returns a list of normalized batch dicts for each provider_item_uuid.
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGProviderItemBatchListLoader(SafeDataLoader):
    """Batch loader returning batch lists keyed by provider_item_uuid."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(PGProviderItemBatchListLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[str]) -> Promise:
        from ....handlers.config import Config
        from ..provider_item_batch import ProviderItemBatchModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[str, List[Dict[str, Any]]] = {}

        if unique_keys:
            try:
                # Query all batches for the given provider_item_uuids
                uuids = [str(k) for k in unique_keys if k]
                if uuids:
                    rows = (
                        session.query(ProviderItemBatchModel)
                        .filter(
                            ProviderItemBatchModel.provider_item_uuid.in_(
                                uuids
                            )
                        )
                        .all()
                    )
                    for row in rows:
                        key = str(row.provider_item_uuid)
                        if key not in key_map:
                            key_map[key] = []
                        key_map[key].append(normalize_row(row))

            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(key, []) for key in keys])


__all__ = ["PGProviderItemBatchListLoader"]