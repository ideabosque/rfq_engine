# Migration Guide: DynamoDB to PostgreSQL

> Project: `rfq_engine`
> Created: 2026-06-21

## Overview

This guide covers migrating data from DynamoDB tables to PostgreSQL tables
while preserving tenant partitioning and data fidelity.

## Migration Order

Entities must be migrated in dependency order to satisfy foreign key
and validation constraints:

1. **Item** → 2. **ProviderItem** → 3. **ProviderItemBatch**
4. **Segment** → 5. **SegmentContact**
6. **FxRate**
7. **CancellationPolicy**
8. **Bundle** → 9. **BundleComponent**
10. **ItemCatalogRef**
11. **ItemPriceTier**
12. **DiscountPrompt**
13. **Request** → 14. **Quote** → 15. **QuoteItem** → 16. **Installment**
17. **File**
18. **AvailabilityHold**

## Migration Script (Planned)

A migration script will be provided at `scripts/migrate_dynamodb_to_postgresql.py`.

### Usage (planned)

```bash
python scripts/migrate_dynamodb_to_postgresql.py \
    --source-region us-east-1 \
    --source-endpoint-url "" \
    --target-host localhost \
    --target-port 5432 \
    --target-user rfq \
    --target-password "..." \
    --target-schema rfq_engine \
    --batch-size 100 \
    --dry-run
```

### Features (planned)

- Migrates entities in dependency order
- Preserves tenant `partition_key` values
- Converts DynamoDB attribute types to PostgreSQL column types
- Handles `MapAttribute` → `JSONB` conversion
- Handles `ListAttribute` → `JSONB` (array) conversion
- Handles `UTCDateTimeAttribute` → `TIMESTAMP(timezone=True)` conversion
- Handles `NumberAttribute` → `NUMERIC` conversion
- Batch processing with configurable batch size
- Dry-run mode for validation without writing
- Retry behavior with exponential backoff
- Idempotent: re-running skips already-migrated records

## Type Mapping

| DynamoDB (PynamoDB) | PostgreSQL | Notes |
| --- | --- | --- |
| `UnicodeAttribute` | `String` / `Text` | `Text` for descriptions |
| `NumberAttribute` | `NUMERIC` | Exact numeric for pricing |
| `BooleanAttribute` | `Boolean` | |
| `UTCDateTimeAttribute` | `TIMESTAMP(timezone=True)` | ISO strings at boundary |
| `MapAttribute` | `JSONB` | Validated in app code |
| `ListAttribute` | `JSONB` | Arrays in JSONB |
| Hash/Range keys | Composite primary key | |
| LSI/GSI | B-tree indexes | |

## Verification

After migration, verify:

1. **Row counts**: `SELECT COUNT(*) FROM items;` — compare with DynamoDB scan count
2. **Field-level spot checks**: Query a few records by UUID and compare field values
3. **Index verification**: Test filter queries that use indexes
4. **Nested data**: Verify JSONB fields contain correct nested structures
5. **Numeric precision**: Compare monetary values for exactness

## Rollback

1. Keep DynamoDB tables intact during migration (do not delete)
2. If rollback is needed, switch `DB_BACKEND` back to `dynamodb`
3. No data loss occurs — DynamoDB remains the source of truth until cutover

## Cutover Steps

1. Run migration script in dry-run mode to validate
2. Run migration script in production mode
3. Verify counts and spot checks
4. Update deployment config: `DB_BACKEND=postgresql`
5. Restart the service
6. Monitor for errors
7. After confidence period, decommission DynamoDB tables

## Status

- [x] PostgreSQL schema and models implemented (Phase 3) — in `models/postgresql/`
- [x] DynamoDB models moved to `models/dynamodb/` with compatibility shims
- [x] Alembic migrations created (18 migrations, 0001-0018)
- [x] Config.CACHE_ENTITY_CONFIG updated to `rfq_engine.models.dynamodb.*`
- [ ] Migration script implementation (Phase 5)
- [ ] Migration script testing (Phase 5)
- [ ] Performance benchmarking (Phase 5)