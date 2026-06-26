# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for price tiers by provider item."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Optional, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


def _normalize_key(key: Tuple[Any, ...]) -> Tuple[str, str, Optional[str]]:
    if len(key) == 2:
        item_uuid, provider_item_uuid = key
        segment_uuid = None
    else:
        item_uuid, provider_item_uuid, segment_uuid = key
    return (
        str(item_uuid) if item_uuid else "",
        str(provider_item_uuid) if provider_item_uuid else "",
        str(segment_uuid) if segment_uuid else None,
    )


class PGItemPriceTierByProviderItemLoader(SafeDataLoader):
    """Batch loader keyed by (item_uuid, provider_item_uuid, segment_uuid)."""

    def batch_load_fn(self, keys: List[Tuple[Any, ...]]) -> Promise:
        from ....handlers.config import Config
        from ..item_price_tier import ItemPriceTierModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys([_normalize_key(key) for key in keys]))
        key_map: Dict[Tuple[str, str, Optional[str]], List[Dict[str, Any]]] = {}

        if unique_keys:
            try:
                for item_uuid, provider_item_uuid, segment_uuid in unique_keys:
                    if not item_uuid or not provider_item_uuid:
                        key_map[(item_uuid, provider_item_uuid, segment_uuid)] = []
                        continue
                    query = session.query(ItemPriceTierModel).filter(
                        ItemPriceTierModel.item_uuid == item_uuid,
                        ItemPriceTierModel.provider_item_uuid == provider_item_uuid,
                    )
                    if segment_uuid:
                        query = query.filter(ItemPriceTierModel.segment_uuid == segment_uuid)
                    rows = query.order_by(ItemPriceTierModel.quantity_greater_then.asc()).all()
                    key_map[(item_uuid, provider_item_uuid, segment_uuid)] = [
                        normalize_row(row) for row in rows
                    ]
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(_normalize_key(key), []) for key in keys])


__all__ = ["PGItemPriceTierByProviderItemLoader"]