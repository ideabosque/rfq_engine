# -*- coding: utf-8 -*-
"""PostgreSQL batch loaders package.

Provides PGRequestLoaders — the PostgreSQL equivalent of the DynamoDB
RequestLoaders container. Uses the same Promise DataLoader pattern but
queries SQLAlchemy models instead of PynamoDB.
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from ....handlers.config import Config


class PGRequestLoaders:
    """Container for PostgreSQL-backed DataLoaders scoped to a single GraphQL request.

    This mirrors the DynamoDB RequestLoaders container but uses
    SQLAlchemy-based batch loaders. Each loader is lazily instantiated
    to avoid importing model modules that may not be ported yet.
    """

    def __init__(self, context: Dict[str, Any], cache_enabled: bool = True):
        logger = context.get("logger")
        self.cache_enabled = cache_enabled
        self._logger = logger
        self._context = context
        self._loaders: Dict[str, Any] = {}

    def _get_loader(self, name: str, loader_cls_name: str, module_path: str):
        """Lazily instantiate a loader."""
        if name not in self._loaders:
            try:
                import importlib

                mod = importlib.import_module(module_path, package=__name__)
                loader_cls = getattr(mod, loader_cls_name)
                self._loaders[name] = loader_cls(
                    logger=self._logger, cache_enabled=self.cache_enabled
                )
            except ImportError as exc:
                raise RuntimeError(
                    f"PostgreSQL loader '{name}' is not implemented: {module_path}"
                ) from exc
        return self._loaders[name]

    @property
    def item_loader(self):
        return self._get_loader(
            "item_loader", "PGItemLoader", ".item_loader"
        )

    @property
    def provider_item_loader(self):
        return self._get_loader(
            "provider_item_loader", "PGProviderItemLoader", ".provider_item_loader"
        )

    @property
    def provider_items_by_item_loader(self):
        return self._get_loader(
            "provider_items_by_item_loader",
            "PGProviderItemsByItemLoader",
            ".provider_items_by_item_loader",
        )

    @property
    def provider_item_batch_loader(self):
        return self._get_loader(
            "provider_item_batch_loader",
            "PGProviderItemBatchLoader",
            ".provider_item_batch_loader",
        )

    @property
    def provider_item_batch_list_loader(self):
        return self._get_loader(
            "provider_item_batch_list_loader",
            "PGProviderItemBatchListLoader",
            ".provider_item_batch_list_loader",
        )

    @property
    def item_price_tier_by_provider_item_loader(self):
        return self._get_loader(
            "item_price_tier_by_provider_item_loader",
            "PGItemPriceTierByProviderItemLoader",
            ".item_price_tier_by_provider_item_loader",
        )

    @property
    def item_price_tier_by_item_loader(self):
        return self._get_loader(
            "item_price_tier_by_item_loader",
            "PGItemPriceTierByItemLoader",
            ".item_price_tier_by_item_loader",
        )

    @property
    def quote_item_list_loader(self):
        return self._get_loader(
            "quote_item_list_loader",
            "PGQuoteItemListLoader",
            ".quote_item_list_loader",
        )

    @property
    def installment_list_loader(self):
        return self._get_loader(
            "installment_list_loader",
            "PGInstallmentListLoader",
            ".installment_list_loader",
        )

    @property
    def discount_prompt_global_loader(self):
        return self._get_loader(
            "discount_prompt_global_loader",
            "PGDiscountPromptGlobalLoader",
            ".discount_prompt_by_scope_loaders",
        )

    @property
    def discount_prompt_by_segment_loader(self):
        return self._get_loader(
            "discount_prompt_by_segment_loader",
            "PGDiscountPromptBySegmentLoader",
            ".discount_prompt_by_scope_loaders",
        )

    @property
    def discount_prompt_by_item_loader(self):
        return self._get_loader(
            "discount_prompt_by_item_loader",
            "PGDiscountPromptByItemLoader",
            ".discount_prompt_by_scope_loaders",
        )

    @property
    def discount_prompt_by_provider_item_loader(self):
        return self._get_loader(
            "discount_prompt_by_provider_item_loader",
            "PGDiscountPromptByProviderItemLoader",
            ".discount_prompt_by_scope_loaders",
        )

    @property
    def segment_loader(self):
        return self._get_loader(
            "segment_loader", "PGSegmentLoader", ".segment_loader"
        )

    @property
    def request_loader(self):
        return self._get_loader(
            "request_loader", "PGRequestLoader", ".request_loader"
        )

    @property
    def quote_loader(self):
        return self._get_loader(
            "quote_loader", "PGQuoteLoader", ".quote_loader"
        )

    @property
    def quotes_by_request_loader(self):
        return self._get_loader(
            "quotes_by_request_loader",
            "PGQuotesByRequestLoader",
            ".quotes_by_request_loader",
        )

    @property
    def files_by_request_loader(self):
        return self._get_loader(
            "files_by_request_loader",
            "PGFilesByRequestLoader",
            ".files_by_request_loader",
        )

    @property
    def segment_contact_loader(self):
        return self._get_loader(
            "segment_contact_loader",
            "PGSegmentContactLoader",
            ".segment_contact_loader",
        )

    @property
    def segment_contact_by_segment_loader(self):
        return self._get_loader(
            "segment_contact_by_segment_loader",
            "PGSegmentContactBySegmentLoader",
            ".segment_contact_by_segment_loader",
        )

    def invalidate_cache(self, entity_type: str, entity_keys: Dict[str, str]):
        """Invalidate cache entries when entities are modified."""
        if not self.cache_enabled:
            return
        # Delegate to individual loader cache invalidation
        # Implementation mirrors the DynamoDB RequestLoaders pattern
        pass


__all__ = ["PGRequestLoaders"]