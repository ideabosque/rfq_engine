# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for quote-item lists by quote."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGQuoteItemListLoader(SafeDataLoader):
    """Batch loader returning quote item lists keyed by quote_uuid."""

    def batch_load_fn(self, keys: List[str]) -> Promise:
        from ....handlers.config import Config
        from ..quote_item import QuoteItemModel

        session = Config.db_session
        unique_keys = [str(k) for k in dict.fromkeys(keys) if k]
        key_map: Dict[str, List[Dict[str, Any]]] = {}

        if unique_keys:
            try:
                rows = (
                    session.query(QuoteItemModel)
                    .filter(QuoteItemModel.quote_uuid.in_(unique_keys))
                    .order_by(QuoteItemModel.updated_at.desc())
                    .all()
                )
                for row in rows:
                    key_map.setdefault(str(row.quote_uuid), []).append(normalize_row(row))
            except Exception as exc:
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(str(key), []) for key in keys])


__all__ = ["PGQuoteItemListLoader"]