# -*- coding: utf-8 -*-
"""PostgreSQL batch loader base helpers."""
from __future__ import print_function

__author__ = "bibow"

from promise.dataloader import DataLoader

from ....handlers.config import Config
from ..base import normalize_row


class SafeDataLoader(DataLoader):
    """Base DataLoader with the same error-isolation behavior as DynamoDB loaders.

    On PostgreSQL, when a query fails mid-transaction the SQLAlchemy session
    enters an ``InFailedSqlTransaction`` state.  Every subsequent query on
    that session will fail until ``session.rollback()`` is issued.  The
    ``dispatch`` override below ensures the shared ``Config.db_session`` is
    rolled back after any batch-load exception, preventing cascading failures
    across unrelated GraphQL resolvers that share the same session.
    """

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(SafeDataLoader, self).__init__(**kwargs)
        self.logger = logger
        self.cache_enabled = cache_enabled and Config.is_cache_enabled()

    def dispatch(self):
        try:
            return super(SafeDataLoader, self).dispatch()
        except Exception as exc:  # pragma: no cover - defensive
            # Rollback the shared PostgreSQL session if a query failed
            # mid-transaction, so subsequent queries on the same session
            # don't cascade into InFailedSqlTransaction errors.
            if Config.DB_BACKEND == "postgresql" and Config.db_session is not None:
                try:
                    Config.db_session.rollback()
                except Exception:
                    pass  # rollback itself can fail if session is already closed
            if self.logger:
                self.logger.exception(exc)
            raise


__all__ = ["SafeDataLoader", "normalize_row"]