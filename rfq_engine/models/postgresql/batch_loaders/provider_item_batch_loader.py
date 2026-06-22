# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for ProviderItemBatch entity.

Batch loads ProviderItemBatchModel records keyed by (provider_item_uuid, batch_no).
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGProviderItemBatchLoader(SafeDataLoader):
    """Batch loader for ProviderItemBatchModel keyed by (provider_item_uuid, batch_no)."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(PGProviderItemBatchLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config
        from ..provider_item_batch import ProviderItemBatchModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        if unique_keys:
            try:
                # Group by provider_item_uuid for efficient querying
                piu_groups: Dict[str, List[str]] = {}
                for piu, bn in unique_keys:
                    piu_str = str(piu) if piu else ""
                    if piu_str not in piu_groups:
                        piu_groups[piu_str] = []
                    piu_groups[piu_str].append(bn if bn else "")

                for piu_str, batch_nos in piu_groups.items():
                    rows = (
                        session.query(ProviderItemBatchModel)
                        .filter(
                            ProviderItemBatchModel.provider_item_uuid.in_(
                                [piu_str]
                            ),
                            ProviderItemBatchModel.batch_no.in_(
                                [bn for bn in batch_nos if bn]
                            ),
                        )
                        .all()
                    )
                    for row in rows:
                        key = (
                            str(row.provider_item_uuid),
                            row.batch_no,
                        )
                        key_map[key] = normalize_row(row)

            except Exception as exc:
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(key) for key in keys])


__all__ = ["PGProviderItemBatchLoader"]