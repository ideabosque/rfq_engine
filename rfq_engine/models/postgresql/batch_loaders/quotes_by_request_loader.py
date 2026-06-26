# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for quote lists by request."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGQuotesByRequestLoader(SafeDataLoader):
    """Batch loader returning quote lists keyed by request_uuid."""

    def batch_load_fn(self, keys: List[str]) -> Promise:
        from ....handlers.config import Config
        from ..quote import QuoteModel

        session = Config.db_session
        unique_keys = [str(k) for k in dict.fromkeys(keys) if k]
        key_map: Dict[str, List[Dict[str, Any]]] = {}

        if unique_keys:
            try:
                rows = (
                    session.query(QuoteModel)
                    .filter(QuoteModel.request_uuid.in_(unique_keys))
                    .order_by(QuoteModel.updated_at.desc())
                    .all()
                )
                for row in rows:
                    key_map.setdefault(str(row.request_uuid), []).append(normalize_row(row))
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(str(key), []) for key in keys])


__all__ = ["PGQuotesByRequestLoader"]