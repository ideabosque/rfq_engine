# Continuous Integration Scenarios SOP — RFQ Engine

> **How to use this SOP.** This Standard Operating Procedure tells the
> Autonomous Integration Testing Specialist *what* to test, *in what order*,
> *against which environment*, and *what "done" means* for `rfq_engine`.
>
> This document was drafted from Phase 1 project discovery on 2026-06-21.
> Fields marked `<pending confirmation>` require explicit user approval
> before any test execution (Phase 8) begins. Per the skill's mandatory
> gate, no provisioning or test execution runs until this SOP is confirmed.

---

## 1. Document Control

| Field | Value |
|---|---|
| SOP title | RFQ Engine Dual-Backend Integration Certification SOP |
| Version | 1.0.0-draft |
| Owner / contact | `<pending confirmation — project maintainer>` |
| Last updated | 2026-06-21 |
| Business domain | `ecommerce` (B2B procurement / RFQ; closest match in `skill-config.yaml`; hospitality sub-domain present) |
| Target environment | `<pending confirmation — dev | staging | qa>` (never `production` without explicit approval) |
| Approval status | `draft` |

## 2. Purpose and Scope

> **Why now.** The repository dispatch boundary adoption is complete and
> enforced by a static adoption guard. DynamoDB is exercised end-to-end.
> PostgreSQL is structurally complete (models, repositories, migrations,
> loaders) and dispatch-verified for all 18 entities, but has not been
> validated against a running PostgreSQL service. This SOP certifies
> dual-backend runtime parity so PostgreSQL can move from
> "implementation-ready" to "production-ready."

- **In scope:**
  - All 18 persisted entities across both `DB_BACKEND` values (`dynamodb`, `postgresql`).
  - **All test operations (create, update, delete, query, list, validate) must be executed through the GraphQL engine** — `RFQEngine.ai_rfq_graphql(query=..., variables=..., endpoint_id=..., part_id=...)` — with `DB_BACKEND` set to the selected backend. No direct database access (SQLAlchemy queries, PynamoDB model calls, or repository-level method calls) is permitted for transaction testing or validation, except for:
    - **Schema provisioning** (Phase 3: `alembic upgrade head`, `Base.metadata.create_all`).
    - **Asset validation gate** (Phase 7-8: row counts, FK orphan checks, auto-calc field verification — these are reconciliation queries, not business operations).
    - **Reconciliation** (Phase 12: referential integrity, cross-system consistency, count verification — same exception as the gate).
  - GraphQL queries, mutations, and nested resolvers routing through `models.repositories` dispatch.
  - Batch loaders (`RequestLoaders` / `PGRequestLoaders`) for the 20-property nested-resolver surface.
  - Backend-dispatched combination helpers (`combine_all_discount_prompts`, `combine_all_item_price_tiers`).
  - Availability hold acquire / confirm / release / expire lifecycle and contention.
  - Pricing calculation: tiered pricing, FX, discount prompts, quote totals, installment ratios.
  - Hospitality modes: `unit`, `per_pax_type`, `occupancy` pricing; service-dated batches; bundle templates.
  - Alembic migrations `0001`-`0018` apply cleanly to a disposable PostgreSQL schema.
  - Cache invalidation behavior after mutations (DynamoDB cache config; PG cache config empty by design).
  - Static adoption guard (no `models.dynamodb` imports in `queries/` / `mutations/` / `types/`).
- **Out of scope:**
  - The `mcp_rfq_processor` companion package (separate service, separate certification).
  - KGE / `inquire_catalog` live external graph endpoints (handler is integrated; live KGE calls require external owner sign-off — see INT-019).
  - AI-driven negotiation logic itself (prompt *storage* and *retrieval* are in scope; AI *decision-making* is not).
  - Performance benchmarking beyond a smoke-level timing check (Phase 5 benchmark work is tracked separately in `DUAL_BACKEND_DEVELOPMENT_PLAN.md`).
  - DynamoDB-to-PostgreSQL data migration execution (covered by `MIGRATION_DYNAMODB_TO_POSTGRESQL.md`; validated separately).
- **System(s) under test:** `rfq_engine` GraphQL engine and its persistence layer (`models/dynamodb`, `models/postgresql`, `models/repositories`), running on AWS Lambda-style invocation against DynamoDB and/or PostgreSQL.

## 3. Environment and Access

| Item | Value / source |
|---|---|
| Environment target | `<pending confirmation — single env for both backends, or separate dev (DynamoDB) + qa (PostgreSQL)>` |
| Base URLs / endpoints | GraphQL schema invoked in-process via `RFQEngine` + `Graphql.fetch_graphql_schema`; no HTTP gateway in scope |
| Credential source | `.env` at repo root for local runs (`aws_access_key_id`, `aws_secret_access_key`, `region_name`, `endpoint_id`, `part_id`, `execute_mode`); `DATABASE_URL` or `PG_HOST`/`PG_PORT`/`PG_USER`/`PG_PASSWORD`/`PG_DB` for PostgreSQL |
| Required env vars | `region_name`, `aws_access_key_id`, `aws_secret_access_key`, `endpoint_id`, `part_id`, `execute_mode` (DynamoDB path); `DATABASE_URL` or `PG_*` (PostgreSQL path); `cache_enabled` (optional) |
| Data stores | DynamoDB (default; 18 tables `are-*`); PostgreSQL (18 tables; SQLAlchemy + Alembic) |
| Messaging / events | None — no queues or event buses in the engine itself |
| Access constraints | AWS credentials scoped to the target DynamoDB tables; PostgreSQL credentials scoped to the disposable `rfq_engine` test schema |
| Provisioning policy | Auto-provision the disposable PostgreSQL schema (`Base.metadata.drop_all` + `create_all`) and DynamoDB test tables when safe; manual approval required for any cloud credential scope change or production access |

> **Names and sources only — never paste secrets, tokens, or connection strings.**

## 4. Dependency Readiness Requirements

> Each dependency must reach all four readiness states before testing begins:
> `available -> configured -> initialized -> operational`.

| Dependency | Type | Health check | Required readiness | Owner |
|---|---|---|---|---|
| DynamoDB (`are-*` tables) | infrastructure | `initialize_tables(logger)` succeeds; `RequestModel.exists()` | operational | `<pending — AWS account owner>` |
| PostgreSQL (disposable schema) | infrastructure | `DATABASE_URL` reachable; `SELECT 1`; `alembic upgrade head` or `Base.metadata.create_all` | initialized | `<pending — DB owner>` |
| AWS credentials (S3 for File) | infrastructure | `boto3.client("s3").list_buckets()` (or scoped equivalent) | configured | `<pending>` |
| `silvaengine_dynamodb_base` | internal (library) | import + `BaseModel` meta initialized | operational | SilvaEngine team |
| `silvaengine_utility` | internal (library) | import + `HybridCacheEngine` instantiable | operational | SilvaEngine team |
| `graphene` / `promise` | internal (library) | import + schema builds | operational | open-source |
| `SQLAlchemy>=1.4` / `psycopg2-binary` / `alembic` | internal (library, PG-only) | import; installed via `rfq-engine[postgresql]` extras | configured | open-source |
| Repository dispatch boundary | internal (module) | `get_repo("item")` resolves under both backends; `get_loaders({})` returns correct loader type | operational | rfq_engine team |
| Alembic migration set `0001`-`0018` | internal (module) | `alembic upgrade head` applies cleanly to empty schema | initialized | rfq_engine team |

## 5. Test Data Requirements

| Asset type | Count | Notes / constraints |
|---|---|---|
| Segments | 3 | Realistic names; one flagged as "Premium" for discount-prompt SEGMENT scope |
| Segment contacts | 5 | Distinct emails; at least one mapped to the Premium segment for email→segment lookup |
| Items | 6 | One per pricing mode (`unit`, `per_pax_type`, `occupancy`) plus 3 legacy `unit` items; realistic UOMs |
| Provider items | 4 | Two providers (`PROV_A`, `PROV_B`); at least one with `availability_mode="require_hold"` |
| Provider item batches | 5 | One service-dated (`service_start_at`/`service_end_at`) with `availability_qty=10`; one unquantified (`availability_qty=null`) |
| Item price tiers | 6 | Cover `unit`, `per_pax_type` (adult/child), and `occupancy` (base + surcharge maps); contiguous quantity ranges |
| Discount prompts | 4 | One per scope: GLOBAL, SEGMENT, ITEM, PROVIDER_ITEM; each with valid contiguous `discount_rules` |
| Cancellation policies | 2 | One linked to a `ProviderItemBatch` for snapshot capture |
| Bundles + components | 1 bundle, 3 components | Package template with `component_role` lodging/transfer/activity |
| FX rates | 2 | One USD→EUR, one EUR→USD for cross-currency quote tests |
| Requests | 3 | One standard B2B; one hospitality multi-component; one bundle-backed |
| Quotes + quote items | 3 quotes, 6+ items | One per request; one with FX; one with discount prompt applied |
| Installments | 3 | One per quote with varying priorities and scheduled dates |
| Files | 2 | Small text + small binary; S3 upload if AWS credentials present |
| Availability holds | 4 tokens | acquire → confirm; acquire → release; acquire → expire; acquire contention |
| Users / roles | 3 | Admin, buyer (`buyer@company.com`), sales rep (`sales@supplier.com`) — used as `updated_by` / `email` |

- **Load order:** master data (segment, item, provider_item, provider_item_batch, fx_rate, cancellation_policy, bundle, bundle_component, discount_prompt, item_price_tier) → customer data (segment_contact) → request → quote → quote_item → installment → file → availability_hold.
- **Data source:** generated by the `prepare_test_data/` seed scripts (under `rfq_engine/tests/prepare_test_data/`), which drive data through the GraphQL engine via the repository dispatch boundary — the same mutations production traffic uses. Each script writes its generated UUIDs to a JSON fixture file next to it, which downstream scripts read to maintain referential integrity. The scripts are backend-agnostic: `DB_BACKEND=dynamodb` or `DB_BACKEND=postgresql` (plus `PG_*` env vars) controls which backend receives the data.

### Seed Script Execution Sequence

The scripts **must** run in dependency order — each script reads the JSON output of its upstream scripts to resolve parent UUIDs. Running out of order causes "not found" rejections or empty-result computations.

| Step | Script | Reads | Writes | Entities created |
|---|---|---|---|---|
| 1 | `prepare_segments_and_contacts.py` | — | `segments_and_contacts.json` | Segment, SegmentContact |
| 2 | `prepare_flight_products.py` | `segments_and_contacts.json` (for segment_uuid) | `flight_products.json` | Item, ProviderItem, CancellationPolicy, ProviderItemBatch, ItemPriceTier, Bundle, BundleComponent |
| 3 | `prepare_fx_rates.py` | `flight_products.json` (for currency pairs) | `fx_rates.json` | FxRate |
| 4 | `prepare_discount_prompts.py` | `segments_and_contacts.json` + `flight_products.json` | `discount_prompts.json` | DiscountPrompt (GLOBAL, SEGMENT, ITEM, PROVIDER_ITEM scopes) |
| 5 | `prepare_requests.py` | `segments_and_contacts.json` + `flight_products.json` | `requests.json` | Request |
| 6 | `prepare_quotes.py` | `requests.json` + `flight_products.json` | `quotes.json` | Quote |
| 7 | `prepare_quote_items.py` | `quotes.json` + `requests.json` + `flight_products.json` | `quote_items.json` | QuoteItem (auto-calculates `price_per_uom` from tier, FX conversion, cancellation snapshot, rolls up quote totals) |
| 8 | `prepare_flight_catalog_refs.py` | `flight_products.json` + KGE | `flight_catalog_refs.json` | ItemCatalogRef (optional — requires KGE) |

**Configurable counts** (env vars, defaults shown):
- `SEED_NUM_SEGMENTS=3`, `SEED_NUM_CONTACTS_PER_SEGMENT=5`
- `SEED_FLIGHT_NUM_ROUTES=5`, `SEED_FLIGHT_BATCHES_PER_ROUTE=2`, `SEED_FLIGHT_NUM_BUNDLES=2`, `SEED_FLIGHT_BUNDLE_SIZE=3`
- `SEED_FX_BASE_CURRENCIES=USD`, `SEED_FX_TARGET_CURRENCIES=EUR,GBP,JPY,CNY,AUD,CAD,SGD,HKD`, `SEED_FX_NUM_DAYS=1`, `SEED_FX_INCLUDE_REVERSE=1`
- `SEED_DISCOUNT_NUM_GLOBAL=3`, `SEED_DISCOUNT_NUM_PER_SEGMENT=2`, `SEED_DISCOUNT_NUM_PER_ITEM=1`, `SEED_DISCOUNT_NUM_PER_PROVIDER_ITEM=1`
- `SEED_REQUEST_NUM_REQUESTS=5`, `SEED_REQUEST_MAX_ITEMS=3`, `SEED_REQUEST_PIN_PROVIDER_PROB=0.6`, `SEED_REQUEST_PIN_BATCH_PROB=0.4`
- `SEED_QUOTE_MIN_PER_REQUEST=1`, `SEED_QUOTE_MAX_PER_REQUEST=3`, `SEED_QUOTE_FX_PROB=0.4`, `SEED_QUOTE_SHIPPING_PROB=0.15`
- `SEED_QITEM_DISCOUNT_PROB=0.4`

**Backend selection** (env vars):
- `DB_BACKEND=dynamodb` (default) — uses `region_name` / `aws_access_key_id` / `aws_secret_access_key` from `tests/.env`
- `DB_BACKEND=postgresql` — uses `PG_HOST` / `PG_PORT` / `PG_USER` / `PG_PASSWORD` / `PG_DB` (or `DATABASE_URL`) from `tests/.env`

**Prerequisites:**
- `pip install faker` (not in core dependencies)
- `tests/.env` configured with `endpoint_id`, `part_id`, `execute_mode=local_for_all`, and backend-specific credentials
- For PostgreSQL: `alembic -c migration/alembic.ini upgrade head` applied first (schema must exist before data loading)

## 6. Execution Order

> Dependency-driven order derived from the Phase 5 relationship matrix
> (parent → child, and the dispatch boundary as the entry point).

### 6.1 Model Dependency Matrix

Every entity has soft foreign keys (UUID strings; not enforced by DynamoDB,
enforced by application logic). A child entity cannot be created until its
parent exists. The table below maps every parent→child relationship, the FK
field on the child, and the seed script that creates the child.

| # | Child entity | Parent entity | FK field on child | Seed script | Notes |
|---|---|---|---|---|---|
| 1 | Segment | — (root) | — | `prepare_segments_and_contacts.py` | Tenant-partitioned master data |
| 2 | SegmentContact | Segment | `segment_uuid` | `prepare_segments_and_contacts.py` | Email-keyed membership; segment must exist first |
| 3 | Item | — (root) | — | `prepare_flight_products.py` | Catalog master; `pricing_mode` drives downstream pricing |
| 4 | CancellationPolicy | — (root) | — | `prepare_flight_products.py` | Independent; linked from ProviderItemBatch |
| 5 | Bundle | — (root) | — | `prepare_flight_products.py` | Reusable package/itinerary template |
| 6 | FxRate | — (root) | — | `prepare_fx_rates.py` | Independent; locked rate copied onto Quote |
| 7 | DiscountPrompt | Segment / Item / ProviderItem | `tags[]` (contains UUID) | `prepare_discount_prompts.py` | Scope-based; tags reference parent UUIDs |
| 8 | ProviderItem | Item | `item_uuid` | `prepare_flight_products.py` | Supplier offering of a catalog item |
| 9 | ProviderItemBatch | ProviderItem | `provider_item_uuid` | `prepare_flight_products.py` | Inventory lot; also references Item + CancellationPolicy |
| 10 | ProviderItemBatch | Item | `item_uuid` (denormalized) | `prepare_flight_products.py` | Denormalized FK for reverse lookups |
| 11 | ProviderItemBatch | CancellationPolicy | `cancellation_policy_uuid` (optional) | `prepare_flight_products.py` | Optional link for snapshot capture |
| 12 | ItemPriceTier | Item | `item_uuid` | `prepare_flight_products.py` | Tier keyed by item; also references ProviderItem + Segment |
| 13 | ItemPriceTier | ProviderItem | `provider_item_uuid` | `prepare_flight_products.py` | Provider-specific pricing |
| 14 | ItemPriceTier | Segment | `segment_uuid` | `prepare_flight_products.py` | Segment-specific pricing |
| 15 | BundleComponent | Bundle | `bundle_uuid` | `prepare_flight_products.py` | Default component in a bundle template |
| 16 | BundleComponent | Item | `item_uuid` | `prepare_flight_products.py` | Default item for the component |
| 17 | BundleComponent | ProviderItem | `provider_item_uuid` (optional) | `prepare_flight_products.py` | Optional default provider |
| 18 | Request | — (root) | — | `prepare_requests.py` | RFQ hub; optionally references Bundle via `bundle_uuid` |
| 19 | Request | Bundle | `bundle_uuid` (optional) | `prepare_requests.py` | When request is for a package template |
| 20 | Quote | Request | `request_uuid` | `prepare_quotes.py` | Supplier response to a request |
| 21 | QuoteItem | Quote | `quote_uuid` | `prepare_quote_items.py` | Line item; auto-calculates `price_per_uom` from ItemPriceTier |
| 22 | QuoteItem | Item | `item_uuid` | `prepare_quote_items.py` | References catalog item |
| 23 | QuoteItem | ProviderItem | `provider_item_uuid` | `prepare_quote_items.py` | References supplier offering |
| 24 | QuoteItem | ProviderItemBatch | `batch_no` (optional) | `prepare_quote_items.py` | Pinned batch for availability + cancellation snapshot |
| 25 | QuoteItem | BundleComponent | `bundle_component_uuid` (optional) | `prepare_quote_items.py` | Back-link to bundle template component |
| 26 | QuoteItem | Segment | `segment_uuid` (via pricing resolution) | `prepare_quote_items.py` | Resolved during tier lookup, not stored directly |
| 27 | Installment | Quote | `quote_uuid` | *(not seeded — runtime mutation)* | Payment schedule; auto-calculates `installment_ratio` from Quote totals |
| 28 | File | Request | `request_uuid` | *(not seeded — runtime mutation)* | Document attachment; requires S3 |
| 29 | AvailabilityHold | ProviderItem | `provider_item_uuid` | *(runtime — availability mutation)* | Durable hold on quantified capacity |
| 30 | AvailabilityHold | ProviderItemBatch | `batch_no` (implicit) | *(runtime — availability mutation)* | Reserves `availability_qty` on the batch |
| 31 | ItemCatalogRef | Item | `item_uuid` | `prepare_flight_catalog_refs.py` (optional) | Maps external KGE node → internal item |
| 32 | ItemCatalogRef | ProviderItem | `provider_item_uuid` (optional) | `prepare_flight_catalog_refs.py` (optional) | Optional provider-specific mapping |

**Cascading delete protection** (parent cannot be deleted while children exist):
- Segment ← SegmentContact, ItemPriceTier, DiscountPrompt
- Item ← ProviderItem, ItemPriceTier, DiscountPrompt
- ProviderItem ← ProviderItemBatch, QuoteItem, ItemPriceTier
- ProviderItemBatch ← QuoteItem (via batch_no)
- Request ← Quote, File
- Quote ← QuoteItem, Installment
- Bundle ← BundleComponent

**Auto-calculated fields** (computed by the repository on insert/update, not caller-supplied):
- `ProviderItemBatch.total_cost_per_uom` = `cost_per_uom + freight_cost_per_uom + additional_cost_per_uom`
- `ProviderItemBatch.guardrail_price_per_uom` = `total_cost_per_uom × (1 + guardrail_margin_per_uom/100)`
- `QuoteItem.price_per_uom` = resolved from `ItemPriceTier` (direct price or margin + batch cost)
- `QuoteItem.subtotal` = `price_per_uom × qty` (with FX conversion from parent Quote)
- `QuoteItem.final_subtotal` = `subtotal - subtotal_discount`
- `QuoteItem.subtotal_native` = native-currency subtotal before FX
- `QuoteItem.request_data.cancellation_policy_snapshot` = snapshot from pinned batch's policy
- `Quote.total_quote_amount` = `Σ QuoteItem.subtotal`
- `Quote.total_quote_discount` = `Σ QuoteItem.subtotal_discount`
- `Quote.final_total_quote_amount` = `total_quote_amount - total_quote_discount + shipping_amount`
- `Quote.rounds` = incremented on every quote/quote_item update
- `Installment.installment_ratio` = `(installment_amount / Quote.final_total_quote_amount) × 100`

### 6.2 Execution Sequence

The certification run proceeds in two phases: **asset loading** (Phase 7 + Phase 8) and **transaction testing** (Phase 9 + Phase 10). **All test assets must be loaded and validated before any transaction scenario executes.**

#### Phase A: Asset Loading (must complete before Phase B)

```text
1. Schema provisioning
   -> alembic upgrade head (PostgreSQL) or initialize_tables (DynamoDB)

2. Seed scripts in dependency order (Section 5 seed-script sequence):
   prepare_segments_and_contacts.py    -> Segment, SegmentContact
   prepare_flight_products.py          -> Item, ProviderItem, CancellationPolicy,
                                          ProviderItemBatch, ItemPriceTier,
                                          Bundle, BundleComponent
   prepare_fx_rates.py                 -> FxRate
   prepare_discount_prompts.py         -> DiscountPrompt (4 scopes)
   prepare_requests.py                 -> Request
   prepare_quotes.py                   -> Quote
   prepare_quote_items.py              -> QuoteItem (auto-calculates pricing,
                                          FX, cancellation snapshot, quote totals)
   prepare_flight_catalog_refs.py      -> ItemCatalogRef (optional, needs KGE)

3. Asset validation gate:
   -> Verify row counts per table (Section 9 reconciliation)
   -> Verify referential integrity (no orphaned children)
   -> Verify auto-calculated fields are populated
      (price_per_uom, subtotal, final_subtotal, total_cost_per_uom,
       guardrail_price_per_uom, quote totals, cancellation snapshots)
   -> GATE: all assets loaded and validated before proceeding
```

#### Phase B: Transaction Testing (executes after Phase A gate passes)

```text
Foundation (dispatch boundary + Config.DB_BACKEND)
  -> Master Data (item, segment, fx_rate, cancellation_policy, bundle,
                  bundle_component, item_catalog_ref, discount_prompt)
  -> Customer (segment_contact)
  -> Product (provider_item, provider_item_batch, item_price_tier)
  -> Pricing (price tier resolution, discount prompt scope hierarchy)
  -> RFQ (request, file)
  -> Quote (quote, quote_item, installment)
  -> Availability (availability_hold: acquire / confirm / release / expire / contention)
  -> Backend Parity (same workflows under DB_BACKEND=postgresql)
  -> Reconciliation (referential integrity, counts, audit fields)
```

**Reason for deviation from the skill default:** the RFQ engine has no
order/fulfillment/billing stages — its terminal workflow is quote +
installment + availability hold. Availability holds intentionally run late
because they depend on provider_item_batch and are the highest-risk
contention surface. Backend parity runs second-to-last so every DynamoDB
scenario is mirrored against PostgreSQL before reconciliation.

### 6.3 Transaction Scenario Dependency Graph

Scenarios depend on data created by earlier scenarios. The table below maps
every inter-scenario dependency: which scenario must pass before this one can
run, and what state it relies on. **Scenarios must execute in this order.**

| # | Scenario | Depends on (must pass first) | State required from upstream |
|---|---|---|---|
| 1 | INT-001 (adoption guard) | — | Source tree clean |
| 2 | INT-002 (dispatch contract) | — | Python deps installed |
| 3 | INT-017 (Alembic migrations) | — (PostgreSQL-only prerequisite) | Empty PostgreSQL schema |
| 4 | INT-003 (Item lifecycle) | INT-001, INT-002 | Dispatch boundary operational; backend reachable |
| 5 | INT-004 (Provider item + batch + tier) | INT-003 | Items exist in the backend |
| 6 | INT-005 (Discount prompt hierarchy) | INT-003, INT-004 | Segment + segment_contact + item + provider_item exist |
| 7 | INT-006 (Request → Quote → QuoteItem) | INT-003, INT-004, INT-005 | Items, provider items, segments, price tiers, discount prompts, contacts all exist |
| 8 | INT-007 (Installment ratio) | INT-006 | Quote exists with `final_total_quote_amount > 0` (rolled up from quote_items) |
| 9 | INT-008 (FX cross-currency) | INT-006 | Quote + quote_item creation path works; FX rate exists |
| 10 | INT-009 (Cancellation snapshot) | INT-004, INT-006 | `ProviderItemBatch.cancellation_policy_uuid` set; quote_item creation works |
| 11 | INT-010 (Bundle template) | INT-004, INT-006 | Bundle + components exist; request + quote_item creation works |
| 12 | INT-011 (Availability hold: acquire → confirm) | INT-004 | `provider_item.availability_mode="require_hold"`; batch with `availability_qty > 0` |
| 13 | INT-012 (Availability hold: release + expire) | INT-011 | Hold acquisition path works; a hold token exists |
| 14 | INT-013 (Availability hold contention) | INT-011, INT-012 | Batch with known `availability_qty`; acquire/release/expire validated |
| 15 | INT-014 (per_pax_type pricing) | INT-004, INT-006 | Item `pricing_mode="per_pax_type"`; tiers per pax_type; quote_item pricing resolution works |
| 16 | INT-015 (occupancy pricing) | INT-004, INT-006 | Item `pricing_mode="occupancy"`; tier with `base_occupancy` + `extra_pax_surcharges`; quote_item pricing resolution works |
| 17 | INT-016 (Backend parity) | INT-003 through INT-010 | All DynamoDB scenarios passed; PostgreSQL schema provisioned (INT-017) |
| 18 | INT-018 (Cache invalidation) | INT-003, INT-006 | Item + quote with items exist; `cache_enabled=true` |
| 19 | INT-019 (inquire_catalog handler) | INT-004 | `ItemCatalogRef` rows exist; KGE mocked |

**Dependency chain (visual):**

```text
INT-001 ──┐
INT-002 ──┤
          ├──> INT-003 ──> INT-004 ──> INT-005 ──┐
          │                                     ├──> INT-006 ──> INT-007
          │                                     │         ├──> INT-008
          │                                     │         ├──> INT-009
          │                                     │         ├──> INT-010
          │                                     │         ├──> INT-014
          │                                     │         └──> INT-015
          │                             │
          │                             ├──> INT-011 ──> INT-012 ──> INT-013
          │                             │
          │                             └──> INT-018
          │
INT-017 ──┘
          │
          └──> INT-016 (depends on INT-003..INT-010 + INT-017)
                 │
                 └──> INT-019 (depends on INT-004)
```

**Critical path (P1 must-pass sequence):**

```text
INT-001 → INT-002 → INT-003 → INT-004 → INT-006 → INT-011 → INT-012 → INT-013 → INT-016 → INT-017
```

**Skipped if upstream fails:** INT-007, INT-008, INT-009, INT-010, INT-014,
INT-015 all skip if INT-006 fails (no quote/quote_item to test against).
INT-013 skips if INT-011 or INT-012 fail (no validated hold lifecycle).

## 7. Integration Scenarios

> Priority drives execution when time is limited (P1 = must pass to certify).
> CI trigger column is `<pending confirmation>` until Section 11 is approved.
>
> **Execution method:** All transaction scenarios (INT-003 through INT-015,
> INT-018) and all automated tests for API operations must be executed through
> the GraphQL engine —
> `RFQEngine.ai_rfq_graphql(query=<GraphQL_document>, variables=<vars>,
> endpoint_id=<eid>, part_id=<pid>)` — with `DB_BACKEND` set to the selected
> backend. Every "Create", "Update", "Delete" step is a GraphQL **mutation**
> (`insertUpdateXxx`, `deleteXxx`). Every "Query", "Verify", "List" step is a
> GraphQL **query** (`xxx`, `xxxList`). No direct repository method calls
> (`get_repo().get()`, `get_repo().insert_update()`, etc.) or raw SQL queries
> are permitted for business-operation testing. The only exceptions are:
> - INT-001 (static source-code guard — no runtime calls)
> - INT-002 (dispatch registry verification — `get_repo()`/`get_loaders()` are
>   registry-level; a GraphQL boot smoke test is added to prove the engine
>   routes through the registry)
> - Phase 12 reconciliation (SQL queries for integrity verification, not
>   business operations)
> - Asset validation gate (Phase 7-8: row counts, FK orphan checks)
>
> **Automated test suite (`pytest`):** The `test_postgresql_repositories.py`
> module must execute item CRUD via GraphQL mutations/queries
> (`insertUpdateItem`, `item`, `itemList`, `deleteItem`) through
> `RFQEngine.ai_rfq_graphql` — not via direct `ItemPGRepository()` method calls.
> All other `pytest` modules (`test_repository_adoption_guard.py`,
> `test_backend_agnostic_dispatch.py`, `test_dual_backend_loaders.py`,
> `test_batch_loaders.py`, `test_nested_resolvers.py`,
> `test_quote_item_g5_g6.py`, `test_helpers.py`) test structural contracts and
> pure logic that do not require GraphQL execution.

### INT-001 — Dispatch boundary adoption (static guard)

| Field | Value |
|---|---|
| **ID** | INT-001 |
| **Name** | No GraphQL module imports `models.dynamodb` directly |
| **Priority** | P1 |
| **Type** | static / structural |
| **CI trigger** | on pull request |
| **Preconditions** | source tree clean |
| **Dependencies** | `models.repositories` |
| **Test data** | none |
| **Steps** | 1. Run `tests/test_repository_adoption_guard.py` |
| **Expected behavior** | All 3 guard tests pass; zero `models.dynamodb` imports in `queries/`/`mutations/`/`types/`; zero direct `insert_update_*`/`delete_*` free-function calls in mutations |
| **Validation points** | `test_no_direct_dynamodb_imports_in_graphql_layer`, `test_no_direct_dynamodb_function_calls_in_mutations`, `test_graphql_layer_uses_repository_boundary` |
| **Cross-system checks** | n/a |

### INT-002 — Dispatch resolves all 18 entities + GraphQL boot verification

| Field | Value |
|---|---|
| **ID** | INT-002 |
| **Name** | `get_repo()` / `get_loaders()` resolve for both backends + GraphQL engine boots and routes through dispatch |
| **Priority** | P1 |
| **Type** | API (dispatch contract) + GraphQL boot |
| **CI trigger** | on pull request |
| **Preconditions** | Python deps installed (including `[postgresql]` extras); PostgreSQL reachable |
| **Dependencies** | `models.repositories.dispatch`, both backend registries, `RFQEngine.ai_rfq_graphql` |
| **Test data** | none (uses seed data already loaded) |
| **Steps** | 1. Run `tests/test_backend_agnostic_dispatch.py` (dispatch registry verification). 2. `query {ping}` via `RFQEngine.ai_rfq_graphql` with `DB_BACKEND=postgresql` — verify GraphQL engine boots. 3. `query itemList(limit: 1)` via `RFQEngine.ai_rfq_graphql` — verify GraphQL routes through dispatch to PostgreSQL and returns data. |
| **Expected behavior** | All 18 entities resolve via `get_repo()` under both backends; both backends register identical entity sets; `get_loaders()` returns correct loader type; `KeyError`/`ValueError` paths documented; GraphQL `ping` returns greeting; `itemList` returns ≥ 1 item from PostgreSQL (not error, not DynamoDB) |
| **Validation points** | `test_both_backends_register_identical_entity_sets`, parametrized `test_get_repo_resolves_*`, GraphQL `ping` response, GraphQL `itemList` response |
| **Cross-system checks** | DynamoDB registry == PostgreSQL registry == `EXPECTED_ENTITIES` (18); GraphQL engine routes to selected `DB_BACKEND` |

### INT-003 — GraphQL CRUD lifecycle for all entity types via GraphQL

| Field | Value |
|---|---|
| **ID** | INT-003 |
| **Name** | GraphQL CRUD lifecycle (create → query → update → list → delete → verify null) for all entity types via `RFQEngine.ai_rfq_graphql` |
| **Priority** | P1 |
| **Type** | end-to-end (GraphQL mutations + queries) |
| **CI trigger** | on pull request (DynamoDB); nightly (PostgreSQL) |
| **Preconditions** | INT-001, INT-002 pass; Config initialized; backend reachable; schema provisioned |
| **Dependencies** | `models.repositories` dispatch, all entity repositories |
| **Test data** | 1 entity per type (created + queried + updated + listed + deleted via GraphQL) |
| **Steps** | For each entity type, execute via `RFQEngine.ai_rfq_graphql`: 1. `mutation insertUpdateXxx` (create) — verify UUID returned. 2. `query xxx(uuid: ...)` — verify fields match. 3. `mutation insertUpdateXxx` (update) — verify field changed. 4. `query xxxList(...)` — verify entity appears in list. 5. `mutation deleteXxx(uuid: ...)` — verify `ok: true`. 6. `query xxx(uuid: ...)` — verify `null`. Entity types: item, segment, segment_contact, provider_item, provider_item_batch, item_price_tier, discount_prompt, cancellation_policy, bundle, bundle_component, fx_rate, item_catalog_ref, request, quote, quote_item, installment, file. AvailabilityHold uses `mutation acquireAvailabilityHold` / `mutation releaseAvailabilityHold` (covered by INT-011/012). |
| **Expected behavior** | Each create returns UUID; each query returns matching fields; each update mutates the target field; each list returns the entity; each delete returns `ok: true`; each post-delete query returns `null`. All operations go through the GraphQL engine → dispatch boundary → selected backend. |
| **Validation points** | entity_created, entity_queried, entity_updated, entity_listed, entity_deleted, post_delete_null — for every entity type |
| **Cross-system checks** | Count persisted == count created; `updated_at` advances on update; no direct repository calls used — all via GraphQL |

### INT-004 — Provider item + batch + price tier hierarchy

| Field | Value |
|---|---|
| **ID** | INT-004 |
| **Name** | Provider item, batch, and contiguous price tiers |
| **Priority** | P1 |
| **Type** | end-to-end |
| **CI trigger** | nightly |
| **Preconditions** | INT-003 items exist |
| **Dependencies** | `provider_item`, `provider_item_batch`, `item_price_tier` |
| **Test data** | 4 provider items, 5 batches, 6 price tiers |
| **Steps** | 1. `mutation insertUpdateProviderItem`. 2. `mutation insertUpdateProviderItemBatch` with costs; verify `totalCostPerUom` and `guardrailPricePerUom` auto-calc in response. 3. `mutation insertUpdateItemPriceTier` in non-monotonic order; verify auto-linking (`quantityLessThen` updated on previous tier). 4. `query itemPriceTierList(itemUuid: ..., providerItemUuid: ..., segmentUuid: ..., quantityValue: 250)`; verify the correct tier returns. 5. `mutation deleteItemPriceTier`; verify re-linking or rejection per business rule. |
| **Expected behavior** | Auto-calculated cost fields correct; tier auto-linking maintains gap-free coverage; `quantityValue` filter selects the containing tier |
| **Validation points** | cost_calculated, tier_auto_linked, quantity_filter_correct |
| **Cross-system checks** | `total_cost_per_uom == cost_per_uom + freight + additional`; tier ranges cover `[0, ∞)` with no gaps |

### INT-005 — Discount prompt scope hierarchy and combination

| Field | Value |
|---|---|
| **ID** | INT-005 |
| **Name** | Discount prompts resolve across GLOBAL → SEGMENT → ITEM → PROVIDER_ITEM |
| **Priority** | P1 |
| **Type** | end-to-end (pricing) |
| **CI trigger** | nightly |
| **Preconditions** | Segment + segment_contact + item + provider_item exist |
| **Dependencies** | `discount_prompt`, `combine_all_discount_prompts` |
| **Test data** | 4 prompts (one per scope) |
| **Steps** | 1. `mutation insertUpdateDiscountPrompt` per scope with valid contiguous `discount_rules`. 2. `query discountPrompts(email: ...)` for a quote item. 3. Verify the combined result merges by priority (PROVIDER_ITEM > ITEM > SEGMENT > GLOBAL). 4. `mutation insertUpdateDiscountPrompt` update the SEGMENT prompt's `discount_rules`; verify merge re-sorts. 5. `mutation insertUpdateDiscountPrompt` mark one prompt `inactive`; `query discountPrompts` verify it drops from the combination. |
| **Expected behavior** | Higher-priority scope wins; inactive prompts excluded; `discount_rules` validation rejects gaps/overlaps/non-increasing percentages |
| **Validation points** | scope_hierarchy_correct, inactive_excluded, rules_validated |
| **Cross-system checks** | Combined `max_discount_percentage` respects the winning prompt's bound |

### INT-006 — Request → Quote → QuoteItem full RFQ workflow

| Field | Value |
|---|---|
| **ID** | INT-006 |
| **Name** | RFQ submission through quote creation with auto-calculated totals |
| **Priority** | P1 |
| **Type** | end-to-end |
| **CI trigger** | pre-release |
| **Preconditions** | Items, provider items, segments, price tiers, contacts exist |
| **Dependencies** | `request`, `quote`, `quote_item`, `item_price_tier`, `installment` |
| **Test data** | 1 request with 2 items, 1 quote, 2 quote items |
| **Steps** | 1. `mutation insertUpdateRequest` (create, status=initial). 2. `mutation insertUpdateRequest` add items; verify auto-transition to `in_progress`. 3. `mutation insertUpdateQuote`. 4. `mutation insertUpdateQuoteItem` (verify `pricePerUom` auto-calculated from tier in response). 5. `mutation insertUpdateQuoteItem` add second quote item. 6. `query quote(requestUuid: ..., quoteUuid: ...)`; verify `totalQuoteAmount`, `totalQuoteDiscount`, `finalTotalQuoteAmount`. 7. `mutation insertUpdateQuote` update shipping; `query quote` verify `finalTotalQuoteAmount` changes and `rounds` increments. |
| **Expected behavior** | Status auto-transitions; `price_per_uom` from tier; `subtotal = price_per_uom × qty`; quote totals are sums of quote items; `rounds` increments on each update |
| **Validation points** | request_status_transition, price_auto_calculated, totals_aggregated, rounds_incremented |
| **Cross-system checks** | `quote.total_quote_amount == Σ quote_item.subtotal`; `final_total == total - discount + shipping` |

### INT-007 — Installment ratio auto-calculation

| Field | Value |
|---|---|
| **ID** | INT-007 |
| **Name** | Installment ratio computed from quote final total |
| **Priority** | P2 |
| **Type** | end-to-end |
| **CI trigger** | nightly |
| **Preconditions** | INT-006 quote exists with `final_total_quote_amount` |
| **Dependencies** | `installment`, `quote` |
| **Test data** | 3 installments |
| **Steps** | 1. `mutation insertUpdateInstallment` with `installmentAmount`. 2. Verify `installmentRatio == (amount / finalTotalQuoteAmount) * 100` in response. 3. `mutation insertUpdateInstallment` create second installment. 4. `query installmentList(quoteUuid: ...)`; verify ordering by `priority`. |
| **Expected behavior** | Ratio auto-calculated; priority ordering correct |
| **Validation points** | ratio_calculated, priority_ordered |
| **Cross-system checks** | `Σ installment_amount` ≤ `final_total_quote_amount` |

### INT-008 — FX cross-currency quote (G5)

| Field | Value |
|---|---|
| **ID** | INT-008 |
| **Name** | Quote with FX rate locked across currencies |
| **Priority** | P2 |
| **Type** | end-to-end |
| **CI trigger** | nightly |
| **Preconditions** | FX rate USD→EUR exists |
| **Dependencies** | `fx_rate`, `quote`, `quote_item` |
| **Test data** | 1 FX rate, 1 quote with `currency=EUR`, `display_currency=USD` |
| **Steps** | 1. `mutation insertUpdateQuote` with `currency=EUR`, `displayCurrency=USD`. 2. `mutation insertUpdateQuote` set `fxRate` to the locked rate. 3. `mutation insertUpdateQuoteItem` create quote item in EUR. 4. `query quoteItem` verify `subtotal` (display) = `subtotalNative * fxRate`. 5. Same-currency quote (EUR→EUR) `mutation insertUpdateQuoteItem` verifies no FX applied. |
| **Expected behavior** | Cross-currency applies locked rate; same-currency skips FX; unconfigured quote has no FX |
| **Validation points** | fx_applied, fx_skipped_same_currency, fx_absent_unconfigured |
| **Cross-system checks** | Display subtotal within tolerance `0.01` of `native × rate` |

### INT-009 — Cancellation policy snapshot (G6)

| Field | Value |
|---|---|
| **ID** | INT-009 |
| **Name** | Engine-owned cancellation policy snapshot captured at quote creation |
| **Priority** | P2 |
| **Type** | end-to-end |
| **CI trigger** | nightly |
| **Preconditions** | `ProviderItemBatch.cancellation_policy_uuid` set |
| **Dependencies** | `cancellation_policy`, `provider_item_batch`, `quote_item` |
| **Test data** | 1 cancellation policy linked to a batch |
| **Steps** | 1. `mutation insertUpdateQuoteItem` from a batch with a pinned policy. 2. `query quoteItem` verify `requestData.cancellationPolicySnapshot` is populated. 3. `mutation insertUpdateCancellationPolicy` update the batch's policy. 4. `query quoteItem` re-query the existing quote_item; verify the snapshot is unchanged (engine-owned, frozen at creation). 5. `mutation insertUpdateQuoteItem` from a batch with no policy; `query quoteItem` verify no snapshot. |
| **Expected behavior** | Snapshot captured when batch has policy; snapshot frozen; absent when batch has no policy |
| **Validation points** | snapshot_captured, snapshot_frozen, snapshot_absent |
| **Cross-system checks** | Snapshot content matches policy at creation time |

### INT-010 — Bundle template → request → quote items

| Field | Value |
|---|---|
| **ID** | INT-010 |
| **Name** | Reusable bundle template expands into grouped quote items |
| **Priority** | P2 |
| **Type** | end-to-end |
| **CI trigger** | nightly |
| **Preconditions** | Bundle + 3 components exist |
| **Dependencies** | `bundle`, `bundle_component`, `request`, `quote_item` |
| **Test data** | 1 bundle (lodging + transfer + activity) |
| **Steps** | 1. `mutation insertUpdateBundle` + `mutation insertUpdateBundleComponent` x3. 2. `mutation insertUpdateRequest` with `bundleUuid`. 3. `mutation insertUpdateQuoteItem` x3, one per component, each with `bundleUuid` + `bundleComponentUuid` + `bundleLabel`. 4. `query quoteItemList(bundleUuid: ...)`; verify all 3 return grouped. |
| **Expected behavior** | Quote items grouped by `bundle_uuid`; each carries `bundle_component_uuid` back-link |
| **Validation points** | bundle_grouping, component_back_link |
| **Cross-system checks** | Component count == 3; all share the same `bundle_uuid` |

### INT-011 — Availability hold: acquire → confirm

| Field | Value |
|---|---|
| **ID** | INT-011 |
| **Name** | Acquire a hold on quantified capacity and confirm it |
| **Priority** | P1 |
| **Type** | end-to-end (workflow) |
| **CI trigger** | pre-release |
| **Preconditions** | `provider_item.availability_mode="require_hold"`; batch with `availability_qty=10` |
| **Dependencies** | `availability_hold`, `provider_item_batch` |
| **Test data** | 1 batch, qty=4 |
| **Steps** | 1. `query checkAvailability(providerItemUuid: ..., serviceStartAt: ..., serviceEndAt: ..., qty: 4)`. 2. `mutation acquireAvailabilityHold(qty: 4)`. 3. Verify `holdToken` + `expiresAt` in response. 4. `query checkAvailability` re-check; verify qty dropped by 4. 5. `mutation confirmAvailabilityHold(holdToken: ...)`. 6. `query checkAvailability` re-check; verify confirmed qty no longer counts as available. |
| **Expected behavior** | Hold reserves capacity; `available` decrements; confirm makes the reservation durable |
| **Validation points** | hold_acquired, capacity_decremented, hold_confirmed |
| **Cross-system checks** | `availability_qty` after acquire == `original - 4` |

### INT-012 — Availability hold: release and expire

| Field | Value |
|---|---|
| **ID** | INT-012 |
| **Name** | Released and expired holds restore capacity |
| **Priority** | P1 |
| **Type** | end-to-end (workflow) |
| **CI trigger** | pre-release |
| **Preconditions** | INT-011 setup |
| **Dependencies** | `availability_hold` |
| **Test data** | 2 holds (one to release, one to expire) |
| **Steps** | 1. `mutation acquireAvailabilityHold(qty: 3)` hold A. 2. `mutation releaseAvailabilityHold(holdToken: ...)` for A. 3. `query checkAvailability` verify capacity restored. 4. `mutation acquireAvailabilityHold(qty: 2)` hold B with short TTL. 5. `mutation expireAvailabilityHold(holdToken: ...)`. 6. `query checkAvailability` verify capacity restored. 7. `mutation releaseAvailabilityHold(holdToken: "unknown")` verify fails closed. |
| **Expected behavior** | Release restores capacity; expiry restores capacity; unknown token is rejected |
| **Validation points** | release_restores, expiry_restores, unknown_token_rejected |
| **Cross-system checks** | Capacity after release/expire == original |

### INT-013 — Availability hold contention (concurrency)

| Field | Value |
|---|---|
| **ID** | INT-013 |
| **Name** | Concurrent acquisitions cannot overbook |
| **Priority** | P1 |
| **Type** | end-to-end (contention) |
| **CI trigger** | pre-release |
| **Preconditions** | Batch with `availability_qty=5` |
| **Dependencies** | `availability_hold` |
| **Test data** | 1 batch |
| **Steps** | 1. Fire N=10 concurrent `mutation acquireAvailabilityHold(qty: 1)` requests. 2. Verify exactly 5 succeed, 5 fail. 3. `query providerItemBatch` verify final `availabilityQty == 0`. |
| **Expected behavior** | Exactly `availability_qty` acquisitions succeed; no overbooking |
| **Validation points** | success_count == 5, failure_count == 5, final_qty == 0 |
| **Cross-system checks** | `Σ confirmed_holds == original_availability_qty` |

### INT-014 — Hospitality per_pax_type pricing

| Field | Value |
|---|---|
| **ID** | INT-014 |
| **Name** | `per_pax_type` pricing with pax breakdown |
| **Priority** | P2 |
| **Type** | end-to-end (pricing) |
| **CI trigger** | nightly |
| **Preconditions** | Item `pricing_mode="per_pax_type"`; tier per pax type |
| **Dependencies** | `item`, `item_price_tier`, `quote_item` |
| **Test data** | 1 item, 2 tiers (adult, child) |
| **Steps** | 1. `mutation insertUpdateItem(pricingMode: "per_pax_type")`. 2. `mutation insertUpdateItemPriceTier` for `adult` and `child`. 3. `mutation insertUpdateQuoteItem` with `paxBreakdown={adult:2, child:1}`, `qty=3`. 4. `query quoteItem` verify `pricePerUom` resolves the correct tier per pax type. |
| **Expected behavior** | Tier matched by pax_type; `subtotal` computed per the active tier |
| **Validation points** | pax_type_matched, subtotal_correct |
| **Cross-system checks** | `subtotal == Σ(pax_count × tier_price_per_uom)` |

### INT-015 — Hospitality occupancy pricing

| Field | Value |
|---|---|
| **ID** | INT-015 |
| **Name** | `occupancy` pricing with base occupancy + surcharges |
| **Priority** | P2 |
| **Type** | end-to-end (pricing) |
| **CI trigger** | nightly |
| **Preconditions** | Item `pricing_mode="occupancy"`; tier with `base_occupancy` and `extra_pax_surcharges` |
| **Dependencies** | `item`, `item_price_tier`, `quote_item` |
| **Test data** | 1 item, 1 occupancy tier |
| **Steps** | 1. `mutation insertUpdateItem(pricingMode: "occupancy")`. 2. `mutation insertUpdateItemPriceTier` with `baseOccupancy={adult:2}`, `extraPaxSurcharges={child:25}`. 3. `mutation insertUpdateQuoteItem` with `paxBreakdown={adult:2, child:1}`, `qty=3` (room-nights). 4. `query quoteItem` verify `subtotal == (200 + 25) * 3 = 675`. |
| **Expected behavior** | Base price applies to included occupancy; surcharge applies to extra pax; multiplied by qty (nights) |
| **Validation points** | base_occupancy_applied, surcharge_applied, nights_multiplied |
| **Cross-system checks** | `subtotal == (base_price + surcharge) × qty` |

### INT-016 — Backend parity: same GraphQL workflow under PostgreSQL

| Field | Value |
|---|---|
| **ID** | INT-016 |
| **Name** | INT-003 through INT-010 pass identically under `DB_BACKEND=postgresql` |
| **Priority** | P1 |
| **Type** | end-to-end (backend parity) |
| **CI trigger** | pre-release |
| **Preconditions** | PostgreSQL disposable schema provisioned; `alembic upgrade head` applied |
| **Dependencies** | All entity repositories (PG), `PGRequestLoaders` |
| **Test data** | Same fixtures as DynamoDB scenarios |
| **Steps** | 1. `Config.initialize(db_backend="postgresql", ...)`. 2. Run INT-003 through INT-010 via `RFQEngine.ai_rfq_graphql` against PostgreSQL. 3. Compare GraphQL responses field-by-field with the DynamoDB run. |
| **Expected behavior** | Identical GraphQL responses (within numeric tolerance); same status transitions; same auto-calculated fields |
| **Validation points** | pg_crud_matches, pg_totals_match, pg_pricing_matches |
| **Cross-system checks** | Per-field diff between DynamoDB and PostgreSQL outputs == 0 (numeric tolerance `0.01`) |

### INT-017 — Alembic migrations apply to empty PostgreSQL

| Field | Value |
|---|---|
| **ID** | INT-017 |
| **Name** | `alembic upgrade head` creates all 18 tables cleanly |
| **Priority** | P1 |
| **Type** | database |
| **CI trigger** | pre-release |
| **Preconditions** | Empty PostgreSQL schema; `DATABASE_URL` set |
| **Dependencies** | `migration/alembic/`, all 18 migration files |
| **Test data** | none |
| **Steps** | 1. Drop all tables. 2. `alembic -c migration/alembic.ini upgrade head`. 3. Verify all 18 tables exist. 4. Verify `alembic_version` table at `0018`. 5. `alembic downgrade -1`; verify last table dropped. 6. `alembic upgrade head`; verify restored. |
| **Expected behavior** | All migrations apply forward and reverse without error; final revision `0018` |
| **Validation points** | migrations_applied, revision_correct, downgrade_works |
| **Cross-system checks** | Table count == 18; `alembic_version.version_num == "0018"` |

### INT-018 — Cache invalidation after mutation (DynamoDB)

| Field | Value |
|---|---|
| **ID** | INT-018 |
| **Name** | Mutating an entity purges its cache entries and cascades |
| **Priority** | P2 |
| **Type** | end-to-end (cache) |
| **CI trigger** | nightly |
| **Preconditions** | `cache_enabled=true`; DynamoDB backend |
| **Dependencies** | `CascadingCachePurger`, `@method_cache`, `CACHE_ENTITY_CONFIG_DYNAMODB` |
| **Test data** | 1 item, 1 quote with items |
| **Steps** | 1. `query item` (populates cache). 2. `mutation insertUpdateItem` (mutation). 3. `query item` again; verify fresh data returned (not stale). 4. `mutation insertUpdateQuoteItem`; `query quote` verify `totalQuoteAmount` cache is invalidated and recomputed. |
| **Expected behavior** | Mutated entity's cache entry purged; dependent caches cascade-purged |
| **Validation points** | cache_purged, cascade_purged, fresh_data_returned |
| **Cross-system checks** | Post-mutation query returns updated field values |

### INT-019 — inquire_catalog handler integration (offline)

| Field | Value |
|---|---|
| **ID** | INT-019 |
| **Name** | `inquire_catalog` returns mapped catalog refs without live KGE |
| **Priority** | P3 |
| **Type** | API (handler) |
| **CI trigger** | nightly |
| **Preconditions** | `ItemCatalogRef` rows exist; KGE handler stubbed/mocked |
| **Dependencies** | `handlers.catalog`, `item_catalog_ref` |
| **Test data** | 2 catalog refs |
| **Steps** | 1. `mutation insertUpdateItemCatalogRef` insert rows. 2. `query inquireCatalog(namespace: ..., query: ...)` with a mocked KGE response. 3. Verify the result maps `nodeId → itemUuid`. 4. Inject a `CatalogHandlerError`; verify the in-band error fields in the GraphQL response. |
| **Expected behavior** | Mapping resolves; handler errors surface as in-band fields, not exceptions |
| **Validation points** | mapping_resolved, error_in_band |
| **Cross-system checks** | Live KGE calls are **out of scope** — requires external owner sign-off |

## 8. Failure and Resilience Scenarios

| Scenario | Injected fault | Expected behavior |
|---|---|---|
| missing_data | Query unknown `item_uuid` / `request_uuid` | Resolver returns `null`; no exception surfaces to GraphQL client |
| invalid_data | Negative `qty`; non-contiguous `discount_rules` (gap or overlap); `greater_than` not increasing | Mutation rejected with validation error; `validate_and_normalize_discount_rules` raises |
| api_failures | Repository `insert_update` raises mid-commit | Transaction rolls back; `session.rollback()` called; error re-raised with traceback logged |
| database_failures | PostgreSQL connection drop mid-query | `pool_pre_ping=True` detects; retry or graceful error; no silent corruption |
| authentication_failures | AWS credentials missing in DynamoDB mode | `Config.initialize` raises; engine fails fast |
| service_outages | DynamoDB table missing / PostgreSQL schema not provisioned | `initialize_tables` raises; tests skip with explicit reason |
| third_party_outages | KGE endpoint unreachable for `inquire_catalog` | `CatalogHandlerError` surfaced as in-band `error_code`/`error_message`; no exception |
| cache_failures | `HybridCacheEngine` miss/stale | SafeDataLoader falls back to fresh query; `normalize_model` normalizes cached shape |
| contention_overbook | Concurrent hold acquisitions exceed `availability_qty` | Exactly `availability_qty` succeed; the rest fail closed; no overbooking |
| unknown_hold_token | `releaseAvailabilityHold` / `confirm` with unknown token | Mutation fails closed; returns error in-band |

## 9. Data Reconciliation Checks

| Check | Rule | Tolerance |
|---|---|---|
| Referential integrity | No orphaned quote_items (every `quote_uuid` resolves to a quote); no orphaned installments | 0 |
| Quote total aggregation | `quote.total_quote_amount == Σ quote_item.subtotal` | amount: 0.01 |
| Quote final total | `final_total_quote_amount == total - discount + shipping` | amount: 0.01 |
| Installment ratio | `installment_ratio == (amount / final_total_quote_amount) × 100` | ratio: 0.01 |
| FX conversion | `subtotal (display) == subtotal_native × fx_rate` | amount: 0.01 |
| Occupancy subtotal | `subtotal == (base_price + surcharge) × qty` | amount: 0.01 |
| Count consistency | Entities created == entities persisted (per type) | 0 |
| Backend parity | DynamoDB result == PostgreSQL result for the same scenario (field-by-field) | numeric: 0.01; otherwise exact |
| Cache freshness | Post-mutation query returns updated field values (no stale reads) | 0 mismatches |
| Tier coverage | Price tier ranges over `[0, ∞)` with no gaps/overlaps | 0 gaps |
| Hold capacity | `Σ confirmed_holds == original_availability_qty - current_availability_qty` | 0 |
| Timestamp drift | `updated_at` advances on every successful mutation | 0 (must strictly increase) |
| Audit completeness | Every `insert_update` sets `updated_by` and `updated_at` | 0 missing |

## 10. Entry and Exit Criteria

**Entry criteria (transaction testing may begin when):**

**Phase A — Asset Loading gate (all must pass before Phase B):**
- Environment validated: `Config.initialize` succeeds for the active backend; `initialize_tables` completes; `SELECT 1` (PostgreSQL) or `RequestModel.exists()` (DynamoDB) passes.
- All P1 dependencies operational: dispatch boundary, repository registry (both backends), `Config.DB_BACKEND` selectable.
- Schema provisioned: `alembic upgrade head` (PostgreSQL) or `initialize_tables` (DynamoDB) completes; all 18 entity tables exist.
- Seed scripts executed in dependency order (Section 5 seed-script sequence): `prepare_segments_and_contacts.py` → `prepare_flight_products.py` → `prepare_fx_rates.py` → `prepare_discount_prompts.py` → `prepare_requests.py` → `prepare_quotes.py` → `prepare_quote_items.py`.
- Asset validation: row counts per table > 0 for all loaded entities; referential integrity clean (no orphaned children); auto-calculated fields populated (`price_per_uom`, `subtotal`, `final_subtotal`, `total_cost_per_uom`, `guardrail_price_per_uom`, quote totals, cancellation snapshots).
- `tests/test_repository_adoption_guard.py` and `tests/test_backend_agnostic_dispatch.py` pass (INT-001, INT-002).

**Phase B — Transaction Testing (executes after Phase A gate passes):**
- All Phase A entry criteria met.
- Scenarios execute in the order defined by Section 6.3 (Transaction Scenario Dependency Graph).
- A scenario may only run if its upstream dependencies (listed in Section 6.3) have passed.

**Exit criteria (certification may be issued when):**
- All P1 scenarios pass (INT-001, INT-002, INT-003, INT-004, INT-005, INT-006, INT-011, INT-012, INT-013, INT-016, INT-017).
- Coverage ≥ 80% of scenarios in Section 7 executed (not skipped).
- No blocking defects open.
- Reconciliation checks (Section 9) all clean within tolerance.
- Backend parity (INT-016) shows zero field-level diffs between DynamoDB and PostgreSQL for the mirrored scenarios.

## 11. CI Trigger and Cadence

| Trigger | Scope run | Required to pass |
|---|---|---|
| On pull request | INT-001, INT-002, INT-003, INT-011 (smoke) | yes — blocks merge |
| Nightly | INT-001 through INT-015 + INT-018 + INT-019 | report only (non-blocking) |
| Pre-release | Full suite INT-001 through INT-019 + resilience (Section 8) + reconciliation (Section 9) | yes — blocks release |

> CI cadence targets are `<pending confirmation>` until the team confirms the
> PR-block vs nightly-report split.

## 12. Reporting and Certification Expectations

### 12.1 Report Format and Location

- **Report format:** `markdown` (default per `skill-config.yaml`).
- **Location:** written to the target project's `docs/` directory:
  - Stable: `docs/integration_certification_report.md` (latest certification).
  - Dated: `docs/live_integration_results_<YYYYMMDD>.md` (per-run archive).
- **Required certification decision:** one of `Integration Certified`, `Ready for UAT`, `Ready for Production`, `Ready with Conditions`, `Not Ready`.
- **Distribution:** `<pending confirmation — test owner + release manager>`.

### 12.2 Required Report Sections

The final report must include these sections (per `references/final-report-template.md`):

1. **Header metadata** — generated-at, project, domain, environment, endpoint, partition, SOP reference, execution order, pass/fail/skipped/blocked counts, certification status.
2. **Executive Summary** — 3-6 sentences: what was certified, against which environment, headline result, blocking issues, certification decision.
3. **Scope** — in scope, out of scope, phases executed, phases skipped (with reason).
4. **Dependency Readiness** — table with Available / Configured / Initialized / Operational per dependency.
5. **Function Results** — one block per call (see Section 12.3 below).
6. **End-to-End Workflow Validation** — table: workflow, steps executed, validation points, result.
7. **Failure and Resilience Results** — table: scenario, injected fault, expected behavior, observed behavior, result.
8. **Data Reconciliation** — table: check, rule, tolerance, observed, result.
9. **Coverage Analysis** — table: area, covered, total, %, notes.
10. **Defect Analysis** — table: ID, severity, title, root cause, affected calls, recommendation.
11. **Open Risks and Mitigation Plan** — table: risk, likelihood, impact, mitigation, owner.
12. **Certification Decision** — status, rationale, conditions, evidence sources.
13. **Sign-off** — role, name, date, decision.

### 12.3 Function Results — Per-Call Recording Format

> Every function, tool, API call, CLI command, pytest invocation, SQL query,
> and **GraphQL operation** executed during the certification run must be
> recorded as a separate block in the Function Results section, **in execution
> order**. This is the evidence chain that grounds the certification decision.

Each call block must contain:

| Field | Required | Description |
|---|---|---|
| **Number** | yes | Sequential call number (1, 2, 3, ...) |
| **Group** | yes | Logical group: `Environment`, `Schema`, `Dependency`, `Seed`, `Tests`, `Transaction`, `Resilience`, `Reconciliation` |
| **Method** | yes | The exact method/function/CLI invoked (e.g. `alembic upgrade head`, `pytest test_postgresql_repositories.py`, `SQLAlchemy SELECT`, `RFQEngine.ai_rfq_graphql`, `prepare_flight_products.py`) |
| **Short description** | yes | One-line summary of what the call does |
| **Status** | yes | `pass`, `fail`, `error`, `skipped`, or `blocked` |
| **Elapsed** | yes | Duration in milliseconds or seconds |
| **Scenario ID** | yes | SOP scenario reference (e.g. `INT-001`, `INT-006`, `Phase 11`) |
| **Arguments** | yes | Exact input arguments as JSON (command args, env vars, SQL parameters, GraphQL variables, function kwargs) |
| **Output** | yes | Returned output as JSON (test results, row counts, query results, API responses, **GraphQL response payload**). Truncate oversized payloads with `... (truncated)` marker, keeping the structurally relevant portion. |
| **Expected** | on failure only | Expected shape or value when status is `fail` or `error` |
| **Error/diff** | on failure only | Error message, status code, or expected-vs-actual diff |

#### GraphQL Call Recording (mandatory for all transaction and resilience scenarios)

Every call to `RFQEngine.ai_rfq_graphql(query=..., variables=..., endpoint_id=..., part_id=...)` must be recorded with the **full GraphQL document** and the **full response payload** — not a summary or paraphrase. This applies to all INT-003 through INT-015, INT-018, INT-019 transaction scenarios and all Phase 11 resilience scenarios.

**Arguments block for a GraphQL call must include:**

```json
{
  "method": "RFQEngine.ai_rfq_graphql",
  "engine_call": {
    "endpoint_id": "gpt",
    "part_id": "nestaging",
    "DB_BACKEND": "postgresql"
  },
  "graphql_document": "mutation InsertUpdateItem($type:String,$name:String,$uom:String,$by:String!){insertUpdateItem(itemType:$type,itemName:$name,uom:$uom,updatedBy:$by){item{itemUuid itemName itemType}}}",
  "graphql_operation": "mutation insertUpdateItem",
  "variables": {
    "type": "test_product",
    "name": "Cert Test Item",
    "uom": "each",
    "by": "cert"
  }
}
```

**Output block for a GraphQL call must include the full response:**

```json
{
  "data": {
    "insertUpdateItem": {
      "item": {
        "itemUuid": "fa18f487-96f7-4c95-a35e-af4bb4e578e6",
        "itemName": "Cert Test Item",
        "itemType": "test_product"
      }
    }
  },
  "errors": null
}
```

**Rules for GraphQL call recording:**

1. **Record the full `graphql_document`** — the complete GraphQL mutation or query string as passed to `ai_rfq_graphql`, including all field selections. Do not abbreviate with `...`.
2. **Record the full `variables`** — the exact variables dict passed. Redact any secret values (e.g. passwords) but keep all business values (UUIDs, amounts, names, dates).
3. **Record the full response `data`** — the complete `data` object from the GraphQL response, including all returned fields. For list queries, include all items (truncate only if > 20 items, with `... (truncated, N items total)` marker).
4. **Record `errors`** — if the GraphQL response contains `errors`, include the full error array with `message`, `locations`, and `path` for each error.
5. **Record `engine_call` context** — the `endpoint_id`, `part_id`, and `DB_BACKEND` used for the call, so the backend selection is auditable.
6. **One block per GraphQL operation** — if a scenario executes 5 mutations and 3 queries, there must be 8 separate Function Results blocks, each with its own `graphql_document`, `variables`, and response.
7. **Group by scenario** — GraphQL calls should be tagged with their Scenario ID (e.g. `INT-003`, `INT-006`) and appear in execution order within the scenario.

**Block template (GraphQL call):**

```markdown
### N. Transaction / `mutation insertUpdateItem` (INT-003 create item via GraphQL)

- Method: `RFQEngine.ai_rfq_graphql`
- Status: `pass`
- Elapsed: `~30 ms`
- Scenario ID: `INT-003`

Arguments:

```json
{
  "method": "RFQEngine.ai_rfq_graphql",
  "engine_call": { "endpoint_id": "gpt", "part_id": "nestaging", "DB_BACKEND": "postgresql" },
  "graphql_document": "mutation InsertUpdateItem($type:String,$name:String,$uom:String,$by:String!){insertUpdateItem(itemType:$type,itemName:$name,uom:$uom,updatedBy:$by){item{itemUuid itemName itemType}}}",
  "graphql_operation": "mutation insertUpdateItem",
  "variables": { "type": "test_product", "name": "Cert Test Item", "uom": "each", "by": "cert" }
}
```

Output:

```json
{
  "data": { "insertUpdateItem": { "item": { "itemUuid": "fa18f487-96f7-4c95-a35e-af4bb4e578e6", "itemName": "Cert Test Item", "itemType": "test_product" } } },
  "errors": null
}
```
```

**General rules (all call types):**

- **Never omit a call.** If 28 calls were executed, there must be 28 blocks.
- **Arguments must be exact.** Record the real env vars, SQL parameters, GraphQL variables, and CLI flags — not paraphrased descriptions.
- **Output must be observed.** Use the actual command output, test result, query response, or GraphQL response payload. Do not infer or fabricate.
- **Truncate wisely.** Large outputs (e.g. 100-row query results, list queries returning > 20 items) should be truncated with `... (truncated, N rows total)` but keep enough to show the structural shape. GraphQL mutations always include full response.
- **Never include secrets.** Credentials, tokens, API keys, and connection strings with passwords must be redacted (e.g. `PG_PASSWORD: "<redacted>"`).
- **Group by phase.** Calls should appear in execution order, grouped by the phase that produced them (Phase 2 environment checks → Phase 3 schema → Phase 7-8 seed → Phase 9 tests → Phase 10 GraphQL transactions → Phase 11 GraphQL resilience → Phase 12 reconciliation).

### 12.4 Minimum Certification Output

The report must include these minimum sections whenever certifying readiness:

- Scope tested
- Dependencies validated, provisioned, configured, initialized, and blocked
- Execution order used
- Tests run with pass, fail, skipped, and blocked counts
- Per-call Function Results: input arguments and output for every call
- Workflow and data integrity findings
- Defects by severity and root cause
- Open risks and mitigation plan
- Final certification status

## 13. Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Test owner | `<pending>` | `<pending>` | `<pending>` |
| Release manager | `<pending>` | `<pending>` | `<pending>` |
| DB owner (PostgreSQL) | `<pending>` | `<pending>` | `<pending>` |
| AWS account owner (DynamoDB) | `<pending>` | `<pending>` | `<pending>` |

---

## Pending Confirmation Items

Before any test execution (Phase 8) begins, the following placeholders need
explicit decisions:

1. **Target environment** (Section 1): single environment for both backends, or separate `dev` (DynamoDB) + `qa` (PostgreSQL)?
2. **SOP owner / contact** (Section 1): who owns this document?
3. **Credential source confirmation** (Section 3): confirm `.env` + `DATABASE_URL`/`PG_*` as the approved secret sources; confirm AWS credential scope.
4. **Dependency owners** (Section 4): who owns DynamoDB, PostgreSQL, and each library dependency for readiness sign-off?
5. **Provisioning policy** (Section 3): confirm auto-provisioning of the disposable PostgreSQL schema (`Base.metadata.drop_all` + `create_all`) is allowed in the target environment.
6. **CI cadence** (Section 11): confirm the PR-block / nightly-report / pre-release-block split.
7. **Distribution list** (Section 12): who receives the certification report?
8. **Sign-off roles** (Section 13): names for test owner, release manager, DB owner, AWS account owner.
9. **Live KGE sign-off** (INT-019): confirm whether live KGE calls are in scope or remain mocked; if live, identify the KGE owner.
10. **Scope confirmation** (Section 2): confirm `mcp_rfq_processor` and data-migration execution remain out of scope for this certification cycle.

Once these are confirmed, the SOP status moves from `draft` to `approved` and
the 13-phase certification (or the agreed subset) may proceed.