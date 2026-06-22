# RFQ Engine Dual-Backend Development Plan

> Project: `rfq_engine`
> Goal: support DynamoDB and PostgreSQL as deployment-selectable persistence backends behind a single GraphQL contract.
> Status: The repository dispatch boundary is **adopted and enforced** by every GraphQL code path — all queries, mutations, and nested resolvers route persistence through `get_repo()` / `get_loaders()`, and a static adoption guard prevents regressions. DynamoDB remains the default and is exercised end-to-end. PostgreSQL is structurally complete (models, repositories, migrations, loaders) and dispatch-verified for all 18 entities, but has **not** yet been validated against a running PostgreSQL service. PostgreSQL repository CRUD tests are scaffolded (`tests/test_postgresql_repositories.py`) and run automatically when a database is available.
> Last reviewed: 2026-06-21
> Verified against source on: 2026-06-21

## Executive Summary

`rfq_engine` historically persisted RFQ data through DynamoDB/PynamoDB models built on `silvaengine_dynamodb_base.BaseModel`. The codebase now runs on a dual-backend structure:

- `DB_BACKEND=dynamodb` (default): PynamoDB models under `rfq_engine.models.dynamodb`, DynamoDB DataLoaders, existing cache/decorator behavior, and DynamoDB utils/validators/combination helpers.
- `DB_BACKEND=postgresql`: SQLAlchemy models under `rfq_engine.models.postgresql`, 18 Alembic migrations, 18 PostgreSQL repositories under `rfq_engine.models.repositories.postgresql`, and PostgreSQL DataLoader coverage for the current nested-resolver surface.

The repository boundary lives in `rfq_engine.models.repositories`. It isolates GraphQL queries, mutations, and nested resolvers from backend-specific persistence details. **All GraphQL persistence calls now flow through this boundary** (`get_repo()` for query/mutation operations, `get_loaders()` for nested-resolver batching, and `models.repositories.utils` for backend-dispatched combination helpers). The PostgreSQL path should be treated as **implementation-ready and validation-incomplete** rather than production-ready: the wiring is real and exercised by smoke tests, but no GraphQL query, mutation, or resolver has yet been executed against a live PostgreSQL database.

> Note on consolidation (2026-06-15): the earlier flat `models/*.py` compatibility shims, the abandoned `models/repo/` tree, and the duplicate `models/postgresql/repos/` directory were removed. Every caller (mutations, queries, types, tests, handlers) imports from the canonical `rfq_engine.models.repositories` boundary; DynamoDB entity modules live under `rfq_engine.models.dynamodb.<entity>`, and PostgreSQL repositories live under `rfq_engine.models.repositories.postgresql/`. There are no top-level model shims and no `models/batch_loaders/` dispatcher module.

## Current Architecture

```text
GraphQL schema, queries, mutations, nested resolvers
        |  (all persistence calls route through the dispatch boundary)
        v
rfq_engine.models.repositories
   dispatch.get_repo(entity_type)        -> active repository
   dispatch.get_loaders(context)         -> active request-scoped loaders
   utils.combine_all_discount_prompts    -> backend-dispatched helpers
   utils.combine_all_item_price_tiers
        |
        +-- DynamoDB implementation
        |      rfq_engine.models.dynamodb
        |      18 PynamoDB entity modules, cache.py, utils.py
        |      batch_loaders/  (RequestLoaders, get_loaders, clear_loaders,
        |                       SafeDataLoader, 17 real loader modules)
        |      rfq_engine.models.repositories.dynamodb  (18 thin wrappers + _base.py)
        |
        +-- PostgreSQL implementation
               rfq_engine.models.postgresql
               18 SQLAlchemy entity modules, base.py, utils.py
               batch_loaders/  (PGRequestLoaders, SafeDataLoader, 17 loader modules)
               rfq_engine.models.repositories.postgresql  (18 repository classes)
               migration/alembic  (18 migrations, 0001-0018)
```

Dispatch rules (verified 2026-06-21):

- `Config.DB_BACKEND` selects the active backend at deployment initialization time (`handlers/config.py:23`, `:330`). Only `"dynamodb"` and `"postgresql"` are valid; any other value raises `ValueError` (`config.py:339`).
- `get_repo(entity_type)` lazily registers and returns the active backend repository (`models/repositories/dispatch.py:33-55`). A `KeyError` is raised if no repository is registered for the requested entity on the active backend.
- `get_loaders(context)` returns request-scoped loaders for the active backend, memoized on `context["batch_loaders"]` (`models/repositories/dispatch.py:58-80`). It raises `ValueError` for an unknown backend.
- GraphQL nested resolvers import `get_loaders` from `rfq_engine.models.repositories.dispatch` (e.g. `types/quote.py:12`). The dispatch-aware loaders select DynamoDB `RequestLoaders` or PostgreSQL `PGRequestLoaders` based on `Config.DB_BACKEND`.
- The combination helpers `combine_all_discount_prompts` and `combine_all_item_price_tiers` are dispatched via `rfq_engine.models.repositories.utils` based on `Config.DB_BACKEND` (e.g. `types/quote.py:156`).

## Repository Adoption Status (verified 2026-06-21)

A source audit on 2026-06-21 confirmed full adoption of the dispatch boundary by production GraphQL code:

- **20 of 20** query modules (`rfq_engine/queries/*.py`) import `get_repo` from `..models.repositories` and call `get_repo(entity).resolve_single(...)` / `.list(...)` / `.count(...)` (111 `get_repo` call sites across queries, mutations, and types).
- **19 of 19** mutation modules import `get_repo` from `..models.repositories` and call `get_repo(entity).insert_update(...)` / `.delete(...)`. No mutation calls DynamoDB `insert_update_*` / `delete_*` functions directly.
- **20 of 20** type modules import `get_loaders` from `..models.repositories.dispatch` (32 `get_loaders` references). The 4 `combine_all_*` references in `types/quote.py` route through `..models.repositories.utils`, which dispatches to the active backend.
- The GraphQL layer contains **zero** direct `models.dynamodb` imports (verified by `tests/test_repository_adoption_guard.py`). The last remaining direct import — a cached-model coercion fallback in `queries/item_price_tier.py` — was removed; `convert_to_types` now uses a single `normalize_to_json` path that handles both normalized dicts and stray PynamoDB instances via `normalize_to_json`'s `attribute_values` branch. A static adoption guard now fails the build if any direct `models.dynamodb` import or direct `insert_update_*` / `delete_*` free-function call reappears in `queries/`, `mutations/`, or `types/`.

Consequence: setting `DB_BACKEND=postgresql` now routes GraphQL persistence through the PostgreSQL repositories and loaders. The remaining gating work has shifted from "wire up the boundary" to "prove runtime parity against a real PostgreSQL database and add backend-agnostic contract tests that fail if the boundary is ever bypassed again."

## Implemented File Layout

```text
rfq_engine/
  handlers/
    config.py
      Config.DB_BACKEND (default "dynamodb")                  # config.py:23
      DynamoDB BaseModel.Meta setup (_initialize_dynamodb_meta, ~L393)
      PostgreSQL scoped-session setup (_initialize_db_session, ~L440)
      Conditional AWS clients for PG mode (_initialize_optional_aws_services, ~L409)
      Backend-aware initialize_tables() (~L471)

  models/
    __init__.py                    # empty
    repositories/
      base.py                       # EntityRepository ABC + RepositoryError family
      dispatch.py                   # get_repo, get_loaders, clear_registry, lazy init
      utils.py                      # backend-dispatched combine_all_discount_prompts /
                                     # combine_all_item_price_tiers
      __init__.py                   # re-exports get_repo, get_loaders, EntityRepository
      dynamodb/                     # 18 thin DynamoDB repository wrappers + _base.py
        __init__.py                 # register_all (18 entries)
      postgresql/                   # 18 PostgreSQL repository classes
        __init__.py                 # register_all (18 entries; ImportError-swallowing)

    dynamodb/
      *.py                          # 18 PynamoDB entity modules + cache.py + utils.py
      batch_loaders/                # __init__.py (RequestLoaders, get_loaders, clear_loaders)
                                     # base.py (SafeDataLoader, normalize_model, Key)
                                     # 17 loader modules
      utils.py                      # initialize_tables, validators, combine_all_discount_prompts,
                                     # combine_all_item_price_tiers

    postgresql/
      base.py                       # declarative_base(), normalize_row, _serialize_value
      utils.py                      # initialize_tables, PG validators, PG combine_* helpers
      *.py                          # 18 SQLAlchemy entity modules
      batch_loaders/                # __init__.py (PGRequestLoaders, 20 lazy properties)
                                     # base.py (SafeDataLoader)
                                     # 17 loader modules

migration/
  alembic.ini
  alembic/
    env.py                          # DATABASE_URL > Config > alembic.ini fallback
    versions/
      0001_create_items.py
      ...
      0018_create_availability_holds.py
```

Note: there is no `models/postgresql/repos/` directory and no `models/batch_loaders/` dispatcher. Those were removed during the 2026-06-15 consolidation.

## Review Findings From 2026-06-21

The earlier revision of this plan over-stated readiness by claiming the dispatch boundary was "not yet consumed by any GraphQL code path." That is no longer accurate: the boundary is now the sole persistence entry point for GraphQL. The corrected findings are:

- GraphQL queries, mutations, and types import `get_repo` / `get_loaders` from `rfq_engine.models.repositories` (the package `__init__.py` re-exports these). No production GraphQL module imports DynamoDB `batch_loaders.get_loaders` or calls DynamoDB `insert_update_*` / `delete_*` functions directly.
- The PostgreSQL repository lazy-registration import target in `models/repositories/dispatch.py` is correct (`dispatch.py:108` imports `rfq_engine.models.repositories.postgresql`).
- PostgreSQL repository files use clean absolute-style relative imports for `handlers`, `types`, and `utils.normalization` (see header docstring in `models/repositories/postgresql/__init__.py`).
- PostgreSQL loader lazy imports pass `package=__name__` correctly; missing loader modules raise explicit errors (`PGRequestLoaders` fails loudly for unresolved loader properties).
- The dispatch-aware `get_loaders` is imported by all 20 type modules, so the PostgreSQL `PGRequestLoaders` surface is now reachable from production code paths (pending database-backed validation).

Smoke checks confirmed:

- PostgreSQL repository registration discovers 18 repositories (`models/repositories/postgresql/__init__.py:23-42`).
- `DB_BACKEND=postgresql` resolves `ItemPGRepository` through `get_repo("item")`.
- `DB_BACKEND=postgresql` resolves `PGRequestLoaders` and all 20 loader properties used by the current nested resolver surface through `get_loaders(context)` (verified by `tests/test_dual_backend_loaders.py`).
- `DB_BACKEND=dynamodb` still resolves DynamoDB `RequestLoaders` through the same dispatch function.

### Implementation details worth tracking

- `models/repositories/postgresql/__init__.py:50` swallows `ImportError` during registration. This keeps a missing optional module from crashing the whole registry, but it also hides genuine import bugs. When a PG repository fails to register in future debugging, this is the first place to look. Recommended follow-up: at minimum log the failure, and consider failing loudly when `DB_BACKEND=postgresql` is the active (non-optional) backend.
- `handlers/config.py:61-181` `CACHE_ENTITY_CONFIG_DYNAMODB` lists 17 entities and omits `availability_hold`. `CACHE_ENTITY_CONFIG_POSTGRESQL` (`:184`) is intentionally empty because PG repositories do not yet use `@method_cache`. If `availability_hold` should participate in cache invalidation, add it explicitly. When PG repositories opt into caching, `CACHE_ENTITY_CONFIG_POSTGRESQL` must be populated in lock-step with the DynamoDB config.
- The direct DynamoDB import previously in `queries/item_price_tier.py:77` has been removed; `convert_to_types` now uses a single `normalize_to_json` path. The static adoption guard in `tests/test_repository_adoption_guard.py` enforces that no direct `models.dynamodb` import reappears in the GraphQL layer.

## Persisted Entities

The dual-backend structure covers these 18 persisted entities:

| Entity | DynamoDB table | PostgreSQL table | Primary access pattern |
| --- | --- | --- | --- |
| Request | `are-requests` | `requests` | `partition_key`, `request_uuid` |
| Quote | `are-quotes` | `quotes` | `request_uuid`, `quote_uuid` |
| QuoteItem | `are-quote_items` | `quote_items` | `quote_uuid`, `quote_item_uuid` |
| Item | `are-items` | `items` | `partition_key`, `item_uuid` |
| ProviderItem | `are-provider_items` | `provider_items` | `partition_key`, `provider_item_uuid` |
| ProviderItemBatch | `are-provider_item_batches` | `provider_item_batches` | `provider_item_uuid`, `batch_no` |
| ItemPriceTier | `are-item_price_tiers` | `item_price_tiers` | `item_uuid`, `item_price_tier_uuid` |
| Segment | `are-segments` | `segments` | `partition_key`, `segment_uuid` |
| SegmentContact | `are-segment_contacts` | `segment_contacts` | `partition_key`, `email` |
| Installment | `are-installments` | `installments` | `quote_uuid`, `installment_uuid` |
| File | `are-files` | `files` | `request_uuid`, `file_name` |
| FxRate | `are-fx_rates` | `fx_rates` | `partition_key`, `fx_rate_uuid` |
| DiscountPrompt | `are-discount_prompts` | `discount_prompts` | `partition_key`, `discount_prompt_uuid` |
| CancellationPolicy | `are-cancellation_policies` | `cancellation_policies` | `partition_key`, `policy_uuid` |
| Bundle | `are-bundles` | `bundles` | `partition_key`, `bundle_uuid` |
| BundleComponent | `are-bundle_components` | `bundle_components` | `partition_key`, `bundle_component_uuid` |
| ItemCatalogRef | `are-item_catalog_refs` | `item_catalog_refs` | `partition_key`, `catalog_ref_uuid` |
| AvailabilityHold | `are-availability_holds` | `availability_holds` | `partition_key`, `hold_token` |

## Repository Contract

Each repository returns normalized dictionaries or explicit scalar results. PynamoDB and SQLAlchemy instances must not leak above the repository boundary.

```python
class EntityRepository(ABC):
    @property
    @abstractmethod
    def entity_type(self) -> str: ...

    @abstractmethod
    def get(self, **keys) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def count(self, **keys) -> int: ...

    @abstractmethod
    def list(self, info, **filters) -> Any: ...

    @abstractmethod
    def insert_update(self, info, **kwargs) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def delete(self, info, **kwargs) -> bool: ...
```

`models/repositories/base.py` also defines `RepositoryError`, `EntityNotFoundError`, and `DependencyExistsError` (lines 54-63). Concrete repositories add an entity-specific `resolve_single(info, **kwargs)` convenience used by query modules to return the GraphQL type instance directly. Entity-specific repository methods are allowed where the existing domain needs them, including price-tier lookup, discount-prompt lookup, availability-hold transitions, cache-purge metadata, and catalog-reference lookup.

## Configuration Contract

`Config.initialize(logger, setting)` owns backend selection and service initialization:

- `setting["db_backend"]` defaults to `"dynamodb"` (`config.py:23`, `:330`).
- DynamoDB mode initializes AWS clients (`_initialize_aws_services`) and PynamoDB `BaseModel.Meta` credentials (`_initialize_dynamodb_meta`, `:393`).
- PostgreSQL mode initializes SQLAlchemy `scoped_session` (`_initialize_db_session`, `:440` with `pool_recycle=7200`, `pool_size=10`, `pool_pre_ping=True`) and only initializes AWS clients when all three AWS credential fields are present (`_initialize_optional_aws_services`, `:409`).
- `initialize_tables` delegates to DynamoDB or PostgreSQL table initialization based on `Config.DB_BACKEND` (`:471`); PostgreSQL path uses `Base.metadata.create_all(checkfirst=True)` and silently skips missing optional model imports.
- PostgreSQL dependencies are optional through `rfq-engine[postgresql]`, which pulls `SQLAlchemy>=1.4`, `psycopg2-binary>=2.9`, and `alembic>=1.10`. These are not in the core dependency list, so DynamoDB-only installs do not require them.

## PostgreSQL Schema Principles

The PostgreSQL schema is not a one-for-one DynamoDB key copy. The intended principles are:

- Preserve tenant ownership with `partition_key` on tenant-owned tables.
- Use UUID columns for UUID identifiers and strings for non-UUID keys such as email, file name, and batch number.
- Use JSONB for flexible PynamoDB map/list shapes unless a relational child table is clearly required.
- Use numeric types for pricing, quantities, and money-like fields.
- Use timezone-aware timestamps (`TIMESTAMP(timezone=True)`, verified in migration `0018`).
- Add foreign keys where lifecycle ownership is clear, while avoiding constraints that would block existing soft relationships.
- Index existing list/filter paths before performance testing.

## Phase Status

### Phase 0: Baseline and Contract Inventory — Complete

Completed:

- Captured the 18 persisted entities and their access patterns.
- Documented cache relationships and batch-loader usage.
- Added `docs/PHASE0_ENTITY_INVENTORY.md`.

### Phase 1: Backend Dispatch With DynamoDB Pass-Through — Complete

Completed:

- Added `Config.DB_BACKEND`, defaulting to `dynamodb`.
- Added repository base and dispatch modules (`models/repositories/base.py`, `dispatch.py`, `utils.py`).
- Added 18 DynamoDB repository wrappers under `models/repositories/dynamodb/`.
- Moved DynamoDB model modules under `models/dynamodb/`.
- Updated cache entity module paths to `rfq_engine.models.dynamodb.*`.
- Added a dispatch-aware `get_loaders` in `models/repositories/dispatch.py` and migrated all 20 type modules to import it.
- Migrated all 20 query modules to `get_repo(entity).resolve_single(...)` / `.list(...)` / `.count(...)`.
- Migrated all 19 mutation modules to `get_repo(entity).insert_update(...)` / `.delete(...)`.
- Migrated nested-resolver combination helpers (`combine_all_discount_prompts`, `combine_all_item_price_tiers`) to backend-dispatched equivalents under `models/repositories/utils.py`.

Still needed (closeout):

- Add focused tests proving DynamoDB behavior remains compatible through the dispatch layer (the static adoption guard in `tests/test_repository_adoption_guard.py` covers the import boundary; runtime behavior parity through the DynamoDB repository wrappers still needs coverage).

### Phase 2: PostgreSQL Foundation — Structurally Complete

Completed:

- Added optional PostgreSQL dependencies in `pyproject.toml` (`[project.optional-dependencies].postgresql`).
- Added SQLAlchemy base and row normalization helpers (`models/postgresql/base.py`).
- Added PostgreSQL session initialization in `Config`.
- Added optional AWS service initialization for PostgreSQL mode.
- Added Alembic configuration (`migration/alembic.ini`, `migration/alembic/env.py`).
- Added PostgreSQL table initialization helpers (`models/postgresql/utils.py`).

Still needed:

- Add disposable PostgreSQL test database fixtures.
- Validate `Config.initialize(..., db_backend="postgresql")` against a real PostgreSQL service.

### Phase 3: Entity Port — Structurally Complete, Validation Incomplete

Completed:

- Added 18 SQLAlchemy entity models under `models/postgresql/` (all define `__all__ = ["<EntityName>Model"]`).
- Added 18 Alembic migration files under `migration/alembic/versions/` (`0001`-`0018`).
- Added 18 PostgreSQL repository classes under `models/repositories/postgresql/`.
- Added PostgreSQL repository registration for all 18 entity types.
- Added PostgreSQL DataLoader modules for the current nested-resolver surface: 17 loader modules plus `PGRequestLoaders` exposing 20 lazy loader properties (request, quote, quote lists, quote item lists, installment lists, file lists, item/provider/segment loaders, price-tier loaders, and discount-prompt scope loaders).

Still needed:

- Add backend-agnostic GraphQL contract tests that run the same suites under both `DB_BACKEND` values (the dispatch contract for all 18 entities is covered by `tests/test_backend_agnostic_dispatch.py`; full GraphQL query/mutation parity under both backends still needs a live PostgreSQL).
- Add PostgreSQL repository CRUD/list tests against a real or disposable database (`tests/test_postgresql_repositories.py` is scaffolded and integration-marked; it auto-skips without `DATABASE_URL`/`PG_HOST`).
- Verify cache invalidation behavior for both backends (and decide whether `availability_hold` should enter `CACHE_ENTITY_CONFIG_DYNAMODB`).
- Verify migration mapping from DynamoDB shapes to PostgreSQL rows.

### Phase 4: Business Flow Parity — Pending

Required validation:

- Request-to-quote lifecycle.
- Quote item pricing, FX, totals, and discount prompt combination.
- Provider item batch availability checks.
- Availability hold acquisition, confirmation, release, expiry, and contention behavior.
- Bundle/component grouping in requests and quote items.
- Catalog reference lookup and inquiry flow.
- File metadata and S3 behavior.
- Cache purge behavior after mutations.

PostgreSQL availability holds need explicit transaction validation. The intended pattern is row-level locking around the capacity row plus hold insert/update in one transaction, then a concurrency test comparing behavior with DynamoDB transactional writes.

### Phase 5: Migration, Performance, and Operations — Pending

Required work:

- Add `migration/migrate_dynamodb_to_postgresql.py` (alongside the existing `migration/alembic/` tree).
- Migrate entities in dependency order while preserving tenant partitioning.
- Verify row counts and field-level samples.
- Document retry behavior and idempotency.
- Benchmark representative GraphQL queries and mutations on both backends.
- Document backup, rollback, and cutover steps.
- Finalize deployment guidance for `DB_BACKEND`.

### Phase 6: Documentation and Cleanup — Partial

Completed:

- Added `docs/DUAL_BACKEND_CONFIG.md`.
- Added `docs/POSTGRESQL_SETUP.md`.
- Added `docs/MIGRATION_DYNAMODB_TO_POSTGRESQL.md`.
- Updated `README.md` with a brief dual-backend overview.
- Removed the flat `models/*.py` shims, the abandoned `models/repo/` tree, and the duplicate `models/postgresql/repos/` directory (2026-06-15 consolidation).
- Updated this plan to reflect the now-adopted state of the repository boundary.

Still needed:

- Reconcile older README sections that still describe the system as DynamoDB-only (e.g. the "Technology Stack" line and the "Database Schema" table that lists only DynamoDB tables).
- Add a backend-agnostic contract test reference to the testing documentation.

## Testing Strategy

Use layered tests instead of waiting for a final end-to-end suite:

| Layer | DynamoDB | PostgreSQL |
| --- | --- | --- |
| Import smoke | Dispatch resolves DynamoDB repositories/loaders | Dispatch resolves PG repositories/loaders |
| Unit | Existing monkey-patched unit tests | Repository normalization and query-building tests |
| Repository | Wrapper parity for existing behavior | SQLAlchemy CRUD/list tests |
| Loader | Existing Promise loader tests | Equivalent PG loader tests |
| GraphQL | Current schema/query/mutation behavior | Same GraphQL contracts under `DB_BACKEND=postgresql` |
| Integration | Reachable DynamoDB | Disposable PostgreSQL database |
| Contention | DynamoDB transactions | PostgreSQL row locks and isolation |
| Migration | DynamoDB source scans | Target inserts and verification |

Current test coverage:

- `tests/test_repository_adoption_guard.py` — static guard ensuring no `queries/`/`mutations/`/`types/` module imports `models.dynamodb` directly or calls DynamoDB `insert_update_*` / `delete_*` free functions, and that each GraphQL layer routes `models.*` imports through `models.repositories`.
- `tests/test_backend_agnostic_dispatch.py` — verifies `get_repo()` resolves all 18 entities under both `DB_BACKEND` values with matching `entity_type`, both backends register identical entity sets, `get_loaders()` returns the correct loader type, and error paths (`KeyError` / `ValueError`) behave as documented.
- `tests/test_dual_backend_loaders.py` — smoke tests verifying dispatch returns `RequestLoaders` for DynamoDB and `PGRequestLoaders` (with all 20 loader properties instantiable) for PostgreSQL.
- `tests/test_postgresql_repositories.py` — integration-marked CRUD/list/pagination tests for `ItemPGRepository` against a disposable PostgreSQL database; auto-skips when `DATABASE_URL` / `PG_HOST` is not reachable.
- The other 17 test files under `rfq_engine/tests/` are existing DynamoDB-focused tests and do not yet exercise the PostgreSQL path.

Minimum next gates:

1. `python -m compileall -q rfq_engine\models\repositories rfq_engine\models\postgresql rfq_engine\models\dynamodb\batch_loaders`
2. Import smoke checks for `get_repo()` and `get_loaders()` under both backends (in `test_dual_backend_loaders.py` and `test_backend_agnostic_dispatch.py`).
3. Static adoption guard in `test_repository_adoption_guard.py` (now in place — fails on re-introduced direct DynamoDB imports).
4. Focused DynamoDB compatibility tests for GraphQL resolvers routing through repositories.
5. PostgreSQL repository tests using a disposable database (`test_postgresql_repositories.py` — runs when `DATABASE_URL` / `PG_HOST` is available).
6. Backend-agnostic GraphQL tests against both `DB_BACKEND` settings (dispatch contract covered; full GraphQL parity pending a live PostgreSQL).

## Acceptance Criteria

Completed or smoke-checked:

- `DB_BACKEND=dynamodb` remains the default.
- `DB_BACKEND=postgresql` has model, repository, and migration scaffolding for all 18 entities.
- Repository dispatch registers all 18 PostgreSQL repositories (verified by `test_backend_agnostic_dispatch.py`).
- Loader dispatch selects DynamoDB or PostgreSQL loaders based on `Config.DB_BACKEND` (verified in isolation and by the backend-agnostic dispatch tests).
- GraphQL queries, mutations, and nested resolvers route persistence through `get_repo()` / dispatch `get_loaders()` / dispatch `combine_*` helpers — enforced by the static adoption guard in `test_repository_adoption_guard.py`.
- The GraphQL layer has zero direct `models.dynamodb` imports.
- PostgreSQL persistence does not require AWS credentials by design.
- Optional `[postgresql]` extras keep DynamoDB-only installs dependency-free of SQLAlchemy/psycopg2/alembic.

Still required before production readiness:

- PostgreSQL repository, loader, and GraphQL contract tests pass against a real or disposable PostgreSQL database (scaffolded in `test_postgresql_repositories.py`; pending a live DB).
- Cache invalidation works for both backends (and decide whether `availability_hold` participates).
- Migration covers all 18 persisted entities with verification.
- Availability hold contention is validated for both DynamoDB and PostgreSQL.
- Documentation clearly separates implemented structure from validated runtime parity.

## Major Risks

| Risk | Severity | Current status | Mitigation |
| --- | --- | --- | --- |
| PG repo registration silently swallows `ImportError` (`models/repositories/postgresql/__init__.py:50`) | Medium | Open | At minimum log the failure; consider failing loudly when `DB_BACKEND=postgresql` is the active backend. |
| `CACHE_ENTITY_CONFIG_DYNAMODB` omits `availability_hold`; `CACHE_ENTITY_CONFIG_POSTGRESQL` is empty | Medium | Open | Decide whether holds participate in cache invalidation; populate PG cache config when PG repos opt into `@method_cache`. |
| PostgreSQL repository methods drift from DynamoDB decorator behavior | High | Open — no DB-backed tests yet | Run `test_postgresql_repositories.py` against a live PostgreSQL; add backend-agnostic GraphQL contract tests under both `DB_BACKEND` values. |
| Availability hold semantics differ by backend | High | Open | Add backend-specific transaction code and contention tests. |
| DynamoDB indexes do not map cleanly to PostgreSQL indexes | Medium | Open | Validate every list/filter path with query plans. |
| Migration loses nested or numeric fidelity | Medium | Open | Use JSONB/numeric types and verify samples/checksums. |
| Optional PostgreSQL dependencies become required for DynamoDB installs | Medium | Partially mitigated | Keep PostgreSQL imports lazy and add DynamoDB-only import tests. |
| Direct DynamoDB imports reappear in the GraphQL layer | Medium | Mitigated | Static adoption guard in `test_repository_adoption_guard.py` fails the build on regression. |

## Immediate Next Work

1. Run `test_postgresql_repositories.py` against a live PostgreSQL (`DATABASE_URL` or `PG_HOST`/`PG_*`), then extend it to cover the remaining 17 repositories beyond `ItemPGRepository`.
2. Add database-backed PostgreSQL loader tests that verify query results, ordering, and discount-prompt JSONB tag matching.
3. Add focused DynamoDB compatibility tests for GraphQL resolvers routing through the repository wrappers (runtime behavior parity, beyond the static guard).
4. Add full backend-agnostic GraphQL contract tests that run the existing DynamoDB suites under `DB_BACKEND=postgresql` as well.
5. Validate `Config.initialize(..., db_backend="postgresql")` against a real PostgreSQL service and run `alembic upgrade head`.
6. Build the DynamoDB-to-PostgreSQL migration script after repository tests define the accepted target shapes.