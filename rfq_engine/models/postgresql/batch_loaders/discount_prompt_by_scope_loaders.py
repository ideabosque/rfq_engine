# -*- coding: utf-8 -*-
"""PostgreSQL discount prompt scope loaders."""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict, List, Optional, Tuple

from promise import Promise
from sqlalchemy import or_
from silvaengine_constants import DiscountPromptScope, DiscountPromptStatus

from .base import SafeDataLoader, normalize_row


def _query_prompts(session, partition_key: str, scope: str, tag: Optional[str] = None):
    from ..discount_prompt import DiscountPromptModel

    query = session.query(DiscountPromptModel).filter(
        DiscountPromptModel.partition_key == partition_key,
        DiscountPromptModel.scope == scope,
        DiscountPromptModel.status == DiscountPromptStatus.ACTIVE,
    )
    if tag:
        query = query.filter(
            or_(
                DiscountPromptModel.tags.contains([str(tag)]),
                DiscountPromptModel.tags.contains(str(tag)),
            )
        )
    return query.order_by(DiscountPromptModel.priority.desc(), DiscountPromptModel.updated_at.desc()).all()


class DiscountPromptGlobalLoader(SafeDataLoader):
    """Batch loader returning active global discount prompts by partition_key."""

    def batch_load_fn(self, keys: List[str]) -> Promise:
        from ....handlers.config import Config

        session = Config.db_session
        key_map: Dict[str, List[Dict[str, Any]]] = {}
        for partition_key in dict.fromkeys(keys):
            try:
                rows = _query_prompts(session, partition_key, DiscountPromptScope.GLOBAL)
                key_map[partition_key] = [normalize_row(row) for row in rows]
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)
                key_map[partition_key] = []
        return Promise.resolve([key_map.get(key, []) for key in keys])


class DiscountPromptBySegmentLoader(SafeDataLoader):
    """Batch loader returning active segment discount prompts."""

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config

        session = Config.db_session
        key_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for partition_key, segment_uuid in dict.fromkeys(keys):
            key = (partition_key, segment_uuid)
            try:
                rows = _query_prompts(
                    session, partition_key, DiscountPromptScope.SEGMENT, segment_uuid
                )
                key_map[key] = [normalize_row(row) for row in rows]
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)
                key_map[key] = []
        return Promise.resolve([key_map.get(key, []) for key in keys])


class DiscountPromptByItemLoader(SafeDataLoader):
    """Batch loader returning active item discount prompts."""

    def batch_load_fn(self, keys: List[Tuple[str, str]]) -> Promise:
        from ....handlers.config import Config

        session = Config.db_session
        key_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for partition_key, item_uuid in dict.fromkeys(keys):
            key = (partition_key, item_uuid)
            try:
                rows = _query_prompts(session, partition_key, DiscountPromptScope.ITEM, item_uuid)
                key_map[key] = [normalize_row(row) for row in rows]
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)
                key_map[key] = []
        return Promise.resolve([key_map.get(key, []) for key in keys])


class DiscountPromptByProviderItemLoader(SafeDataLoader):
    """Batch loader returning active provider-item discount prompts."""

    def batch_load_fn(self, keys: List[Tuple[str, str, str]]) -> Promise:
        from ....handlers.config import Config

        session = Config.db_session
        key_map: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
        for partition_key, item_uuid, provider_item_uuid in dict.fromkeys(keys):
            key = (partition_key, item_uuid, provider_item_uuid)
            try:
                rows = _query_prompts(
                    session,
                    partition_key,
                    DiscountPromptScope.PROVIDER_ITEM,
                    provider_item_uuid,
                )
                key_map[key] = [normalize_row(row) for row in rows]
            except Exception as exc:
                # Rollback the shared PG session to clear any
                # InFailedSqlTransaction state before the next query.
                try:
                    session.rollback()
                except Exception:
                    pass
                if self.logger:
                    self.logger.exception(exc)
                key_map[key] = []
        return Promise.resolve([key_map.get(key, []) for key in keys])


PGDiscountPromptGlobalLoader = DiscountPromptGlobalLoader
PGDiscountPromptBySegmentLoader = DiscountPromptBySegmentLoader
PGDiscountPromptByItemLoader = DiscountPromptByItemLoader
PGDiscountPromptByProviderItemLoader = DiscountPromptByProviderItemLoader

__all__ = [
    "DiscountPromptGlobalLoader",
    "DiscountPromptBySegmentLoader",
    "DiscountPromptByItemLoader",
    "DiscountPromptByProviderItemLoader",
    "PGDiscountPromptGlobalLoader",
    "PGDiscountPromptBySegmentLoader",
    "PGDiscountPromptByItemLoader",
    "PGDiscountPromptByProviderItemLoader",
]