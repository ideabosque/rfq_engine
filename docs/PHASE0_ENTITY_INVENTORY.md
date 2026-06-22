# Phase 0: Entity Inventory and Backend Contract Checklist

> Project: `rfq_engine`
> Created: 2026-06-21
> Updated: 2026-06-21 — DynamoDB models moved to `models/dynamodb/`, PostgreSQL models added at `models/postgresql/`.
> Purpose: Capture existing DynamoDB behavior and map to the dual-backend implementation.

## Entity Summary (18 Entities)

### 1. Item

| Field | Details |
| --- | --- |
| DynamoDB table | `are-items` |
| PynamoDB class | `ItemModel` |
| Module | `rfq_engine.models.dynamodb.item` (shim at `rfq_engine.models.dynamodb.item`) |
| Hash key | `partition_key` |
| Range key | `item_uuid` |
| LSIs | `item_type-index` (partition_key, item_type), `updated_at-index` (partition_key, updated_at) |
| Attributes | endpoint_id, part_id, item_type, item_name, item_description, pricing_mode, uom, item_external_id, created_at, updated_by, updated_at |
| GraphQL types | ItemType, ItemListType |
| Cache entity config | module=item, getter=get_item, cache_keys=[partition_key, item_uuid] |
| Cache relationships | → provider_item, → item_price_tier, → discount_prompt |
| Functions | get_item, _get_item, get_item_count, get_item_type, resolve_item, resolve_item_list, insert_update_item, delete_item |
| Delete guard | Checks provider_item_list.total > 0 before deleting |
| Batch loaders | ItemLoader (by partition_key, item_uuid) |
| Special methods | resolve_item supports lookup by item_external_id |

### 2. ProviderItem

| Field | Details |
| --- | --- |
| DynamoDB table | `are-provider_items` |
| PynamoDB class | `ProviderItemModel` |
| Module | `rfq_engine.models.dynamodb.provider_item` |
| Hash key | `partition_key` |
| Range key | `provider_item_uuid` |
| LSIs | `item_uuid-index` (partition_key, item_uuid), `provider_corp_external_id-index` (partition_key, provider_corp_external_id), `provider_item_external_id-index` (partition_key, provider_item_external_id), `updated_at-index` (partition_key, updated_at) |
| Attributes | item_uuid, provider_corp_external_id, provider_item_external_id, base_price_per_uom, item_spec(MapAttribute), availability_mode, created_at, updated_by, updated_at |
| GraphQL types | ProviderItemType, ProviderItemListType |
| Cache entity config | module=provider_item, getter=get_provider_item, cache_keys=[partition_key, provider_item_uuid] |
| Cache relationships | → provider_item_batch, → item_price_tier, → discount_prompt |
| Batch loaders | ProviderItemLoader, ProviderItemsByItemLoader |

### 3. ProviderItemBatch

| Field | Details |
| --- | --- |
| DynamoDB table | `are-provider_item_batches` |
| PynamoDB class | `ProviderItemBatchModel` |
| Module | `rfq_engine.models.dynamodb.provider_item_batches` |
| Hash key | `provider_item_uuid` |
| Range key | `batch_no` |
| LSIs | `item_uuid-index` (provider_item_uuid, item_uuid), `updated_at-index` (provider_item_uuid, updated_at) |
| Attributes | item_uuid, partition_key, expired_at, produced_at, service_start_at, service_end_at, cost_per_uom, freight_cost_per_uom, additional_cost_per_uom, total_cost_per_uom, guardrail_margin_per_uom, guardrail_price_per_uom, slow_move_item, in_stock, availability_qty, currency, cancellation_policy_uuid, created_at, updated_by, updated_at |
| GraphQL types | ProviderItemBatchType, ProviderItemBatchListType |
| Batch loaders | ProviderItemBatchLoader, ProviderItemBatchListLoader |

### 4. ItemPriceTier

| Field | Details |
| --- | --- |
| DynamoDB table | `are-item_price_tiers` |
| PynamoDB class | `ItemPriceTierModel` |
| Module | `rfq_engine.models.dynamodb.item_price_tier` |
| Hash key | `item_uuid` |
| Range key | `item_price_tier_uuid` |
| LSIs | `provider_item_uuid-index` (item_uuid, provider_item_uuid), `segment_uuid-index` (item_uuid, segment_uuid), `updated_at-index` (item_uuid, updated_at) |
| Attributes | provider_item_uuid, segment_uuid, partition_key, quantity_greater_then, quantity_less_then, pax_type, margin_per_uom, price_per_uom, currency, base_occupancy(MapAttribute), extra_pax_surcharges(MapAttribute), status, created_at, updated_by, updated_at |
| GraphQL types | ItemPriceTierType, ItemPriceTierListType |
| Batch loaders | ItemPriceTierByItemLoader, ItemPriceTierByProviderItemLoader |
| Special | Used by combine_all_item_price_tiers in models/dynamodb/utils.py |

### 5. Segment

| Field | Details |
| --- | --- |
| DynamoDB table | `are-segments` |
| PynamoDB class | `SegmentModel` |
| Module | `rfq_engine.models.dynamodb.segment` |
| Hash key | `partition_key` |
| Range key | `segment_uuid` |
| LSIs | `provider_corp_external_id-index` (partition_key, provider_corp_external_id), `updated_at-index` (partition_key, updated_at) |
| Attributes | provider_corp_external_id, endpoint_id, part_id, segment_name, segment_description, created_at, updated_by, updated_at |
| GraphQL types | SegmentType, SegmentListType |
| Cache relationships | → segment_contact, → item_price_tier, → discount_prompt |
| Batch loaders | SegmentLoader |

### 6. SegmentContact

| Field | Details |
| --- | --- |
| DynamoDB table | `are-segment_contacts` |
| PynamoDB class | `SegmentContactModel` |
| Module | `rfq_engine.models.dynamodb.segment_contact` |
| Hash key | `partition_key` |
| Range key | `email` |
| LSIs | `consumer_corp_external_id-index` (partition_key, consumer_corp_external_id), `segment_uuid-index` (partition_key, segment_uuid), `updated_at-index` (partition_key, updated_at) |
| Attributes | segment_uuid, contact_uuid, consumer_corp_external_id, created_at, updated_by, updated_at |
| GraphQL types | SegmentContactType, SegmentContactListType |
| Batch loaders | SegmentContactLoader, SegmentContactBySegmentLoader |

### 7. Request

| Field | Details |
| --- | --- |
| DynamoDB table | `are-requests` |
| PynamoDB class | `RequestModel` |
| Module | `rfq_engine.models.dynamodb.request` |
| Hash key | `partition_key` |
| Range key | `request_uuid` |
| LSIs | `email-index` (partition_key, email), `updated_at-index` (partition_key, updated_at) |
| Attributes | email, endpoint_id, part_id, request_title, request_description, billing_address(MapAttribute), shipping_address(MapAttribute), items(ListAttribute of MapAttribute), notes, bundle_uuid, status, expired_at, created_at, updated_by, updated_at |
| GraphQL types | RequestType, RequestListType |
| Cache relationships | → quote, → file |
| Batch loaders | RequestLoader |
| Delete guard | Checks quote count before deleting |

### 8. Quote

| Field | Details |
| --- | --- |
| DynamoDB table | `are-quotes` |
| PynamoDB class | `QuoteModel` |
| Module | `rfq_engine.models.dynamodb.quote` |
| Hash key | `request_uuid` |
| Range key | `quote_uuid` |
| LSIs | `provider_corp_external_id-index` (request_uuid, provider_corp_external_id), `updated_at-index` (request_uuid, updated_at) |
| Attributes | provider_corp_external_id, sales_rep_email, partition_key, shipping_method, shipping_amount, total_quote_amount, total_quote_discount, final_total_quote_amount, currency, display_currency, fx_rate, fx_rate_locked_at, rounds, notes, status, created_at, updated_by, updated_at |
| GraphQL types | QuoteType, QuoteListType |
| Cache relationships | → quote_item, → installment |
| Batch loaders | QuoteLoader, QuotesByRequestLoader |
| Delete guard | Checks quote_item count before deleting |

### 9. QuoteItem

| Field | Details |
| --- | --- |
| DynamoDB table | `are-quote_items` |
| PynamoDB class | `QuoteItemModel` |
| Module | `rfq_engine.models.dynamodb.quote_item` |
| Hash key | `quote_uuid` |
| Range key | `quote_item_uuid` |
| LSIs | `provider_item_uuid-index` (quote_uuid, provider_item_uuid), `item_uuid-index` (quote_uuid, item_uuid), `item_uuid-provider_item_uuid-index` (item_uuid, provider_item_uuid), `updated_at-index` (quote_uuid, updated_at) |
| Attributes | provider_item_uuid, item_uuid, batch_no, request_uuid, partition_key, request_data(MapAttribute), price_per_uom, qty, pax_breakdown(MapAttribute), bundle_uuid, bundle_label, bundle_component_uuid, subtotal, subtotal_discount, final_subtotal, currency, subtotal_native, notes, hold_token, hold_expires_at, created_at, updated_by, updated_at |
| GraphQL types | QuoteItemType, QuoteItemListType |
| Batch loaders | QuoteItemListLoader |
| Delete guard | Checks installment count before deleting |

### 10. Installment

| Field | Details |
| --- | --- |
| DynamoDB table | `are-installments` |
| PynamoDB class | `InstallmentModel` |
| Module | `rfq_engine.models.dynamodb.installment` |
| Hash key | `quote_uuid` |
| Range key | `installment_uuid` |
| LSIs | `updated_at-index` (quote_uuid, updated_at) |
| Attributes | partition_key, request_uuid, priority, salesorder_no, payment_method, scheduled_date, installment_ratio, installment_amount, status, created_at, updated_by, updated_at |
| GraphQL types | InstallmentType, InstallmentListType |
| Batch loaders | InstallmentListLoader |

### 11. File

| Field | Details |
| --- | --- |
| DynamoDB table | `are-files` |
| PynamoDB class | `FileModel` |
| Module | `rfq_engine.models.dynamodb.file` |
| Hash key | `request_uuid` |
| Range key | `file_name` |
| LSIs | `email-index` (request_uuid, email), `updated_at-index` (request_uuid, updated_at) |
| Attributes | email, partition_key, created_at, updated_by, updated_at |
| GraphQL types | FileType, FileListType |
| Batch loaders | FilesByRequestLoader |
| Special | Uses S3 for file storage; email is a range key (not UUID) |

### 12. FxRate

| Field | Details |
| --- | --- |
| DynamoDB table | `are-fx_rates` |
| PynamoDB class | `FxRateModel` |
| Module | `rfq_engine.models.dynamodb.fx_rate` |
| Hash key | `partition_key` |
| Range key | `fx_rate_uuid` |
| LSIs | `currency_pair_date-index` (partition_key, currency_pair_date), `updated_at-index` (partition_key, updated_at) |
| Attributes | source_currency, target_currency, rate, currency_pair_date, rate_date, provider, notes, status, created_at, updated_by, updated_at |
| GraphQL types | FxRateType, FxRateListType |

### 13. DiscountPrompt

| Field | Details |
| --- | --- |
| DynamoDB table | `are-discount_prompts` |
| PynamoDB class | `DiscountPromptModel` |
| Module | `rfq_engine.models.dynamodb.discount_prompt` |
| Hash key | `partition_key` |
| Range key | `discount_prompt_uuid` |
| LSIs | `scope-index` (partition_key, scope), `updated_at-index` (partition_key, updated_at) |
| Attributes | scope, tags(ListAttribute), discount_prompt, conditions(ListAttribute), discount_rules(ListAttribute of MapAttribute), priority, status, created_at, updated_by, updated_at |
| GraphQL types | DiscountPromptType, DiscountPromptListType |
| Special | Used by combine_all_discount_prompts in models/dynamodb/utils.py with 4 scopes (GLOBAL, SEGMENT, ITEM, PROVIDER_ITEM) |
| Batch loaders | DiscountPromptGlobalLoader, DiscountPromptBySegmentLoader, DiscountPromptByItemLoader, DiscountPromptByProviderItemLoader |

### 14. CancellationPolicy

| Field | Details |
| --- | --- |
| DynamoDB table | `are-cancellation_policies` |
| PynamoDB class | `CancellationPolicyModel` |
| Module | `rfq_engine.models.dynamodb.cancellation_policy` |
| Hash key | `partition_key` |
| Range key | `policy_uuid` |
| LSIs | `provider_item_uuid-index` (partition_key, provider_item_uuid), `updated_at-index` (partition_key, updated_at) |
| Attributes | provider_item_uuid, label, description, tiers(MapAttribute), notes_template_uuid, status, created_at, updated_by, updated_at |
| GraphQL types | CancellationPolicyType, CancellationPolicyListType |

### 15. Bundle

| Field | Details |
| --- | --- |
| DynamoDB table | `are-bundles` |
| PynamoDB class | `BundleModel` |
| Module | `rfq_engine.models.dynamodb.bundle` |
| Hash key | `partition_key` |
| Range key | `bundle_uuid` |
| LSIs | `bundle_code-index` (partition_key, bundle_code), `updated_at-index` (partition_key, updated_at) |
| Attributes | bundle_code, bundle_name, bundle_type, description, extra(MapAttribute), status, created_at, updated_by, updated_at |
| GraphQL types | BundleType, BundleListType |
| Cache relationships | → bundle_component |
| Delete guard | Checks bundle_component count before deleting |

### 16. BundleComponent

| Field | Details |
| --- | --- |
| DynamoDB table | `are-bundle_components` |
| PynamoDB class | `BundleComponentModel` |
| Module | `rfq_engine.models.dynamodb.bundle_component` |
| Hash key | `partition_key` |
| Range key | `bundle_component_uuid` |
| LSIs | `bundle_uuid-index` (partition_key, bundle_uuid), `updated_at-index` (partition_key, updated_at) |
| Attributes | bundle_uuid, item_uuid, provider_item_uuid, component_role, required(BooleanAttribute), default_qty(NumberAttribute), sort_order(NumberAttribute), extra(MapAttribute), status, created_at, updated_by, updated_at |
| GraphQL types | BundleComponentType, BundleComponentListType |

### 17. ItemCatalogRef

| Field | Details |
| --- | --- |
| DynamoDB table | `are-item_catalog_refs` |
| PynamoDB class | `ItemCatalogRefModel` |
| Module | `rfq_engine.models.dynamodb.item_catalog_ref` |
| Hash key | `partition_key` |
| Range key | `catalog_ref_uuid` |
| LSIs | `namespace_node_key-index` (partition_key, namespace_node_key), `item_lookup_key-index` (partition_key, item_lookup_key), `updated_at-index` (partition_key, updated_at) |
| Attributes | namespace, node_id, namespace_node_key, extra(MapAttribute), item_uuid, item_lookup_key, provider_item_uuid, status, created_at, updated_by, updated_at |
| GraphQL types | ItemCatalogRefType, ItemCatalogRefListType |
| Special | find_item_catalog_refs function for multi-node lookup, resolve_inquire_catalog |

### 18. AvailabilityHold

| Field | Details |
| --- | --- |
| DynamoDB table | `are-availability_holds` |
| PynamoDB class | `AvailabilityHoldModel` |
| Module | `rfq_engine.models.dynamodb.availability_hold` |
| Hash key | `partition_key` |
| Range key | `hold_token` |
| Attributes | provider_item_uuid, batch_no, quote_uuid, quote_item_uuid, qty, service_start_at, service_end_at, status, expires_at, created_at, updated_at, updated_by |
| GraphQL types | AvailabilityResultType (query result type) |
| Special | Backend-specific atomic implementation needed. DynamoDB uses conditional transactions. PostgreSQL needs SELECT...FOR UPDATE + row locks. |
| Handlers | handlers/availability/handler.py (acquire, release, confirm, expire), handlers/availability/expiry_scanner.py |
| GraphQL mutations | AcquireAvailabilityHold, ReleaseAvailabilityHold, ConfirmAvailabilityHold, ExpireAvailabilityHold |
| GraphQL query | check_availability |

## Cache Entity Config Summary

All 17 entities in `Config.CACHE_ENTITY_CONFIG` (AvailabilityHold is not cached):
- request, quote, quote_item, segment, segment_contact, item, provider_item, provider_item_batch, item_price_tier, installment, file, discount_prompt, fx_rate, cancellation_policy, bundle, bundle_component, item_catalog_ref

## Cache Dependency Relationships

| Parent | Children |
| --- | --- |
| request | quote, file |
| bundle | bundle_component |
| quote | quote_item, installment |
| segment | segment_contact, item_price_tier, discount_prompt |
| item | provider_item, item_price_tier, discount_prompt |
| provider_item | provider_item_batch, item_price_tier, discount_prompt |

## Backend Contract Checklist (Per Entity)

For each entity, the repository implementation must cover:

- [x] `get(**keys)` — Return one normalized entity dict or None
- [x] `count(**keys)` — Return matching row count for existence checks
- [x] `list(info, **filters)` — Return the same list/connection shape expected by GraphQL
- [x] `insert_update(info, **kwargs)` — Create or update one entity, return normalized dict
- [x] `delete(info, **kwargs)` — Delete one entity or return blocked-delete behavior
- [x] Entity-specific methods (e.g., price tier lookup, discount prompt by scope, availability hold atomic operations)
- [ ] Cache invalidation behavior verified (Phase 4)
- [x] DataLoader coverage for nested resolvers

## Test Inventory

| Test file | Type | Notes |
| --- | --- | --- |
| test_helpers.py | Unit | Offline test helpers |
| test_nested_resolvers.py | Nested resolvers | Tests DataLoader-based nested resolution |
| test_inquire_catalog.py | Integration | Catalog inquiry flow |
| test_hospitality_pilot.py | Integration | Hospitality-specific scenarios |
| test_gap_closure_development.py | Integration | Gap closure scenarios |
| test_hardening_pilot.py | Integration | Hardening scenarios |
| test_quote_item_g2_occupancy.py | Unit | QuoteItem G2 occupancy calculation |
| test_quote_item_g5_g6.py | Unit | QuoteItem G5/G6 scenarios |

## DynamoDB Regression Command

```bash
# Run focused unit tests (offline, no DynamoDB required)
cd rfq_engine && python -m pytest rfq_engine/tests/ -m unit -v

# Run all tests (requires DynamoDB connection for integration tests)
cd rfq_engine && python -m pytest rfq_engine/tests/ -v
```

## Notes

- DynamoDB models have been moved to `models/dynamodb/` with compatibility shims at original `models/*.py` paths.
- PostgreSQL models are at `models/postgresql/` with repositories at `models/repositories/postgresql/`.
- All 18 entities have SQLAlchemy models, PG repositories, Alembic migrations (0001-0018), and PG batch loaders (where applicable).
- `Config.CACHE_ENTITY_CONFIG` module paths updated to `rfq_engine.models.dynamodb.*`.
- The 18 entities have significant cross-dependencies through cache relationships, batch loaders, and shared utility functions (combine_all_discount_prompts, combine_all_item_price_tiers).
- The availability hold entity requires backend-specific atomic transaction semantics (DynamoDB conditional transactions vs PostgreSQL `SELECT...FOR UPDATE`).