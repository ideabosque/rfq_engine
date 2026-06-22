# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for installment lists by quote."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List

from promise import Promise

from .base import SafeDataLoader, normalize_row


class PGInstallmentListLoader(SafeDataLoader):
    """Batch loader returning installment lists keyed by quote_uuid."""

    def batch_load_fn(self, keys: List[str]) -> Promise:
        from ....handlers.config import Config
        from ..installment import InstallmentModel

        session = Config.db_session
        unique_keys = [str(k) for k in dict.fromkeys(keys) if k]
        key_map: Dict[str, List[Dict[str, Any]]] = {}

        if unique_keys:
            try:
                rows = (
                    session.query(InstallmentModel)
                    .filter(InstallmentModel.quote_uuid.in_(unique_keys))
                    .order_by(InstallmentModel.priority.asc(), InstallmentModel.updated_at.desc())
                    .all()
                )
                for row in rows:
                    key_map.setdefault(str(row.quote_uuid), []).append(normalize_row(row))
            except Exception as exc:
                if self.logger:
                    self.logger.exception(exc)

        return Promise.resolve([key_map.get(str(key), []) for key in keys])


__all__ = ["PGInstallmentListLoader"]