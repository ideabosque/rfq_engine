# Migration

This folder contains PostgreSQL schema migration assets for `rfq_engine`.

- `alembic.ini`: Alembic configuration for the PostgreSQL backend.
- `alembic/`: Alembic environment, revision template, and schema revision files.

Run schema migrations from the repository root:

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://user:password@localhost:5432/rfq_engine"
alembic -c migration/alembic.ini upgrade head
```

These files manage PostgreSQL schema evolution only. Data migration from DynamoDB to PostgreSQL is tracked separately in `docs/MIGRATION_DYNAMODB_TO_POSTGRESQL.md`.