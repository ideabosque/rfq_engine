# -*- coding: utf-8 -*-
"""Smoke tests for dual-backend DataLoader dispatch."""
from __future__ import print_function

from rfq_engine.handlers.config import Config
from rfq_engine.models.repositories.dispatch import clear_registry, get_loaders


PG_LOADER_PROPERTIES = [
    "item_loader",
    "provider_item_loader",
    "provider_items_by_item_loader",
    "provider_item_batch_loader",
    "provider_item_batch_list_loader",
    "item_price_tier_by_provider_item_loader",
    "item_price_tier_by_item_loader",
    "quote_item_list_loader",
    "installment_list_loader",
    "discount_prompt_global_loader",
    "discount_prompt_by_segment_loader",
    "discount_prompt_by_item_loader",
    "discount_prompt_by_provider_item_loader",
    "segment_loader",
    "request_loader",
    "quote_loader",
    "quotes_by_request_loader",
    "files_by_request_loader",
    "segment_contact_loader",
    "segment_contact_by_segment_loader",
]


def test_get_loaders_dispatches_dynamodb_by_default():
    original_backend = Config.DB_BACKEND
    try:
        Config.DB_BACKEND = "dynamodb"
        clear_registry()
        loaders = get_loaders({})
        assert type(loaders).__name__ == "RequestLoaders"
    finally:
        Config.DB_BACKEND = original_backend
        clear_registry()


def test_postgresql_loader_surface_is_complete():
    original_backend = Config.DB_BACKEND
    try:
        Config.DB_BACKEND = "postgresql"
        clear_registry()
        loaders = get_loaders({})
        assert type(loaders).__name__ == "PGRequestLoaders"
        for name in PG_LOADER_PROPERTIES:
            loader = getattr(loaders, name)
            assert loader is not None, name
            assert hasattr(loader, "load"), name
    finally:
        Config.DB_BACKEND = original_backend
        clear_registry()