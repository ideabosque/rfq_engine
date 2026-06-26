# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for Quote entity."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Tuple

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGQuoteLoader(SafeDataLoader):
    """Batch loader for QuoteModel records keyed by (request_uuid, quote_uuid)."""

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config
        from ..quote import QuoteModel

        session = Config.db_session
        unique_keys = list(dict.fromkeys(keys))
        key_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        if unique_keys:
            try:
                request_groups: Dict[str, List[str]] = {}
                for request_uuid, quote_uuid in unique_keys:
                    request_groups.setdefault(str(request_uuid), []).append(str(quote_uuid))

                for request_uuid, quote_uuids in request_groups.items():
                    rows = (
                        session.query(QuoteModel)
                        .filter(
                            QuoteModel.request_uuid == request_uuid,
                            QuoteModel.quote_uuid.in_([u for u in quote_uuids if u]),
                        )
                        .all()
                    )
                    for row in rows:
                        key_map[(str(row.request_uuid), str(row.quote_uuid))] = normalize_row(row)
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get((str(key[0]), str(key[1]))) for key in keys])


__all__ = ["PGQuoteLoader"]