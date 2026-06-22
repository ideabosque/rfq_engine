# -*- coding: utf-8 -*-
"""PostgreSQL repositories for the PostgreSQL backend.

All PG repository files live under models/repositories/postgresql/.
Import paths are clean:
  from ...postgresql.base import normalize_row       # models/postgresql/base.py
  from ...postgresql.item import ItemModel            # models/postgresql/item.py
  from ..base import EntityRepository  # models/repositories/base.py
  from ....handlers.config import Config   # rfq_engine/handlers/config.py
  from ....types.item import ItemType      # rfq_engine/types/item.py
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Dict

from ..base import EntityRepository


def register_all(registry: Dict[str, EntityRepository]) -> None:
    """Register all PostgreSQL repositories into the given registry dict."""
    _repos = [
        ("item_repo", "ItemPGRepository"),
        ("provider_item_repo", "ProviderItemPGRepository"),
        ("provider_item_batch_repo", "ProviderItemBatchPGRepository"),
        ("segment_repo", "SegmentPGRepository"),
        ("segment_contact_repo", "SegmentContactPGRepository"),
        ("fx_rate_repo", "FxRatePGRepository"),
        ("cancellation_policy_repo", "CancellationPolicyPGRepository"),
        ("bundle_repo", "BundlePGRepository"),
        ("bundle_component_repo", "BundleComponentPGRepository"),
        ("item_catalog_ref_repo", "ItemCatalogRefPGRepository"),
        ("item_price_tier_repo", "ItemPriceTierPGRepository"),
        ("discount_prompt_repo", "DiscountPromptPGRepository"),
        ("request_repo", "RequestPGRepository"),
        ("quote_repo", "QuotePGRepository"),
        ("quote_item_repo", "QuoteItemPGRepository"),
        ("installment_repo", "InstallmentPGRepository"),
        ("file_repo", "FilePGRepository"),
        ("availability_hold_repo", "AvailabilityHoldPGRepository"),
    ]
    for module_name, class_name in _repos:
        try:
            import importlib
            mod = importlib.import_module(f".{module_name}", package=__name__)
            repo_cls = getattr(mod, class_name)
            repo = repo_cls()
            registry[repo.entity_type] = repo
        except ImportError:
            pass


__all__ = ["register_all"]