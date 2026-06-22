# -*- coding: utf-8 -*-
"""PostgreSQL table initialization and shared utilities.

Only imported when DB_BACKEND=postgresql.
"""
from __future__ import print_function

__author__ = "bibow"

import logging
from typing import Any, Dict, List

from .base import Base


def initialize_tables(logger: logging.Logger, db_session: Any) -> None:
    """Create all PostgreSQL tables that have been imported.

    This uses SQLAlchemy metadata.create_all() which is idempotent —
    it only creates tables that don't already exist.
    """
    # Import all model modules so their SQLAlchemy classes register
    # with the Base.metadata
    _import_all_models()

    engine = db_session.get_bind()
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("PostgreSQL tables initialized (create_all with checkfirst=True).")


def _import_all_models() -> None:
    """Import all PostgreSQL model modules to register them with Base.metadata."""
    model_modules = [
        ".item",
        ".provider_item",
        ".provider_item_batch",
        ".segment",
        ".segment_contact",
        ".fx_rate",
        ".cancellation_policy",
        ".bundle",
        ".bundle_component",
        ".item_catalog_ref",
        ".item_price_tier",
        ".discount_prompt",
        ".request",
        ".quote",
        ".quote_item",
        ".installment",
        ".file",
        ".availability_hold",
    ]
    for mod_name in model_modules:
        try:
            __import__(f"rfq_engine.models.postgresql{mod_name}", fromlist=["x"])
        except ImportError:
            # Model not yet ported — skip silently
            logger = logging.getLogger(__name__)
            logger.debug(f"PostgreSQL model not yet available: {mod_name}")


# --- Shared validation helpers (PostgreSQL equivalents of DynamoDB utils) ----

def validate_item_exists(partition_key: str, item_uuid: str) -> bool:
    """Validate if an item exists in the PostgreSQL database."""
    from .item import ItemModel
    from ...handlers.config import Config

    session = Config.db_session
    count = (
        session.query(ItemModel)
        .filter(
            ItemModel.partition_key == partition_key,
            ItemModel.item_uuid == item_uuid,
        )
        .count()
    )
    return count > 0


def validate_provider_item_exists(
    partition_key: str, provider_item_uuid: str
) -> bool:
    """Validate if a provider item exists in the PostgreSQL database."""
    from .provider_item import ProviderItemModel
    from ...handlers.config import Config

    session = Config.db_session
    count = (
        session.query(ProviderItemModel)
        .filter(
            ProviderItemModel.partition_key == partition_key,
            ProviderItemModel.provider_item_uuid == provider_item_uuid,
        )
        .count()
    )
    return count > 0


def validate_batch_exists(provider_item_uuid: str, batch_no: str) -> bool:
    """Validate if a batch exists for a given provider item."""
    from .provider_item_batch import ProviderItemBatchModel
    from ...handlers.config import Config

    session = Config.db_session
    count = (
        session.query(ProviderItemBatchModel)
        .filter(
            ProviderItemBatchModel.provider_item_uuid == provider_item_uuid,
            ProviderItemBatchModel.batch_no == batch_no,
        )
        .count()
    )
    return count > 0


def validate_bundle_exists(partition_key: str, bundle_uuid: str) -> bool:
    """Validate if a bundle exists in the PostgreSQL database."""
    from .bundle import BundleModel
    from ...handlers.config import Config

    session = Config.db_session
    count = (
        session.query(BundleModel)
        .filter(
            BundleModel.partition_key == partition_key,
            BundleModel.bundle_uuid == bundle_uuid,
        )
        .count()
    )
    return count > 0


# --- Backend-parallel combination helpers -----------------------------------
#
# These mirror models/dynamodb/utils.py:combine_all_discount_prompts and
# combine_all_item_price_tiers. Both rely solely on loader property names
# that match 1:1 between RequestLoaders (DynamoDB) and PGRequestLoaders
# (PostgreSQL), so the control flow is identical. The only divergence is
# that the PostgreSQL price-tier helper returns plain normalized dicts
# (the shape the PG loaders already produce), whereas the DynamoDB helper
# returns PynamoDB ItemPriceTierModel shells for the legacy query layer.


def combine_all_discount_prompts(
    partition_key: str,
    email: str,
    quote_items: List[Dict[str, Any]],
    loaders: Any,
) -> Any:
    """Combine discount prompts from all hierarchical scopes and deduplicate.

    Mirrors models/dynamodb/utils.py:combine_all_discount_prompts. The PG
    discount-prompt loaders already return normalized dicts, so the merge
    step is identical (normalize_to_json is idempotent on dicts).
    """
    from promise import Promise
    from silvaengine_utility import Debugger

    from ...utils.normalization import normalize_to_json

    Debugger.info(
        variable=f"{__name__}:combine_all_discount_prompts",
        stage=__name__,
    )

    seen_uuids = set()
    global_promise = loaders.discount_prompt_global_loader.load(partition_key)

    segment_contact_promise = None
    if email:
        segment_contact_promise = loaders.segment_contact_loader.load(
            (partition_key, email)
        )

    item_promises = []
    provider_item_promises = []
    unique_item_uuids = set()
    unique_provider_items = set()

    if quote_items:
        for qi in quote_items:
            item_uuid = qi.get("item_uuid")
            provider_item_uuid = qi.get("provider_item_uuid")
            if item_uuid:
                unique_item_uuids.add(item_uuid)
            if item_uuid and provider_item_uuid:
                unique_provider_items.add((item_uuid, provider_item_uuid))

        for item_uuid in unique_item_uuids:
            item_promises.append(
                loaders.discount_prompt_by_item_loader.load((partition_key, item_uuid))
            )
        for item_uuid, provider_item_uuid in unique_provider_items:
            provider_item_promises.append(
                loaders.discount_prompt_by_provider_item_loader.load(
                    (partition_key, item_uuid, provider_item_uuid)
                )
            )

    def load_segment_prompts_and_merge(segment_contact):
        promises_to_resolve = [global_promise]
        if segment_contact and segment_contact.get("segment_uuid"):
            segment_uuid = segment_contact["segment_uuid"]
            segment_promise = loaders.discount_prompt_by_segment_loader.load(
                (partition_key, segment_uuid)
            )
            promises_to_resolve.append(segment_promise)
        promises_to_resolve.extend(item_promises)
        promises_to_resolve.extend(provider_item_promises)

        def merge_prompts(prompt_lists):
            merged = []
            for prompt_list in prompt_lists:
                for prompt in prompt_list or []:
                    prompt_uuid = prompt.get("discount_prompt_uuid")
                    if prompt_uuid and prompt_uuid not in seen_uuids:
                        seen_uuids.add(prompt_uuid)
                        merged.append(normalize_to_json(prompt))
            return merged

        return Promise.all(promises_to_resolve).then(merge_prompts)

    if segment_contact_promise:
        return segment_contact_promise.then(load_segment_prompts_and_merge)
    return load_segment_prompts_and_merge(None)


def combine_all_item_price_tiers(
    partition_key: str,
    email: str,
    quote_items: List[Dict[str, Any]],
    loaders: Any,
) -> Any:
    """Combine item price tiers for quote items using batch loaders.

    Mirrors models/dynamodb/utils.py:combine_all_item_price_tiers but
    returns plain normalized dicts (the shape the PG loaders produce),
    not PynamoDB ItemPriceTierModel shells. The query layer's
    ``convert_to_types`` must construct ``ItemPriceTierType`` from a dict
    instead of from a PynamoDB model.
    """
    from promise import Promise

    def process_with_segment(segment_contact):
        seg_uuid = segment_contact.get("segment_uuid") if segment_contact else None

        item_keys = set()
        item_data_map: Dict[Any, List[Dict[str, Any]]] = {}

        for item in quote_items:
            item_uuid = item.get("item_uuid")
            provider_item_uuid = item.get("provider_item_uuid")
            if item_uuid and provider_item_uuid:
                key = (item_uuid, provider_item_uuid)
                item_keys.add(key)
                item_data_map.setdefault(key, []).append(item)

        tier_promises = []
        key_list = list(item_keys)
        for item_uuid, provider_item_uuid in key_list:
            tier_promises.append(
                loaders.item_price_tier_by_provider_item_loader.load(
                    (item_uuid, provider_item_uuid, seg_uuid)
                )
            )

        def process_tiers(all_tier_lists):
            result_tiers = []
            for idx, tier_list in enumerate(all_tier_lists):
                if not tier_list:
                    continue
                key = key_list[idx]
                items_for_key = item_data_map.get(key, [])
                for item in items_for_key:
                    item_qty = float(item.get("qty", 0))
                    for tier_dict in tier_list:
                        qty_greater = tier_dict.get("quantity_greater_then", 0)
                        qty_less = tier_dict.get("quantity_less_then", float("inf"))
                        if qty_greater <= item_qty < qty_less:
                            result_tiers.append(tier_dict)
            return result_tiers

        if not tier_promises:
            return Promise.resolve([])
        return Promise.all(tier_promises).then(process_tiers)

    if email:
        return loaders.segment_contact_loader.load((partition_key, email)).then(
            process_with_segment
        )
    return process_with_segment(None)