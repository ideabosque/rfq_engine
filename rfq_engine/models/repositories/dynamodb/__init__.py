# -*- coding: utf-8 -*-
"""DynamoDB repositories — thin wrappers over existing PynamoDB model functions.

Each entity has its own repo file. The register_all function instantiates
all 18 repositories and registers them with the dispatch registry.
"""
from __future__ import print_function

__author__ = "bibow"

from typing import Dict

from ..base import EntityRepository


def register_all(registry: Dict[str, EntityRepository]) -> None:
    """Register all DynamoDB repositories into the given registry dict."""
    from .item_repo import ItemRepository
    from .provider_item_repo import ProviderItemRepository
    from .provider_item_batch_repo import ProviderItemBatchRepository
    from .segment_repo import SegmentRepository
    from .segment_contact_repo import SegmentContactRepository
    from .request_repo import RequestRepository
    from .quote_repo import QuoteRepository
    from .quote_item_repo import QuoteItemRepository
    from .installment_repo import InstallmentRepository
    from .file_repo import FileRepository
    from .fx_rate_repo import FxRateRepository
    from .discount_prompt_repo import DiscountPromptRepository
    from .cancellation_policy_repo import CancellationPolicyRepository
    from .bundle_repo import BundleRepository
    from .bundle_component_repo import BundleComponentRepository
    from .item_catalog_ref_repo import ItemCatalogRefRepository
    from .item_price_tier_repo import ItemPriceTierRepository
    from .availability_hold_repo import AvailabilityHoldRepository

    repos = [
        ItemRepository(),
        ProviderItemRepository(),
        ProviderItemBatchRepository(),
        SegmentRepository(),
        SegmentContactRepository(),
        RequestRepository(),
        QuoteRepository(),
        QuoteItemRepository(),
        InstallmentRepository(),
        FileRepository(),
        FxRateRepository(),
        DiscountPromptRepository(),
        CancellationPolicyRepository(),
        BundleRepository(),
        BundleComponentRepository(),
        ItemCatalogRefRepository(),
        ItemPriceTierRepository(),
        AvailabilityHoldRepository(),
    ]
    for repo in repos:
        registry[repo.entity_type] = repo


__all__ = ["register_all"]