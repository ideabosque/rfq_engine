# Dual-Backend Configuration Guide

> Project: `rfq_engine`
> Created: 2026-06-21

## Overview

`rfq_engine` supports two persistence backends:

- **DynamoDB** (default): Uses PynamoDB models via `silvaengine_dynamodb_base`. Models are in `models/dynamodb/`.
- **PostgreSQL**: Uses SQLAlchemy models with a scoped session. Models are in `models/postgresql/`.

Backend selection is **deployment-time** (not per-request), controlled by the `DB_BACKEND` setting. A repository dispatch boundary (`models/repositories/`) routes all persistence operations to the configured backend.

## Configuration

### DynamoDB (Default)

```python
setting = {
    "db_backend": "dynamodb",  # optional, this is the default
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "initialize_tables": True,  # optional
}
```

No additional dependencies required. The existing PynamoDB behavior is preserved.

### PostgreSQL

```python
setting = {
    "db_backend": "postgresql",
    "db_host": "localhost",
    "db_port": 5432,
    "db_user": "rfq",
    "db_password": "...",
    "db_schema": "rfq_engine",
    # AWS credentials are optional (needed only for S3 file storage)
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "initialize_tables": True,  # optional
}
```

Install PostgreSQL dependencies:

```bash
pip install rfq-engine[postgresql]
```

## Backend Selection Rules

1. `DB_BACKEND` defaults to `"dynamodb"` if not specified.
2. Only `"dynamodb"` and `"postgresql"` are valid values.
3. Backend selection is read once during `Config.initialize()` — it cannot
   be changed per request.
4. PostgreSQL mode does **not** require AWS credentials for persistence.
   AWS clients (S3, SQS, Lambda) are initialized only if credentials are present.
5. DynamoDB mode does **not** import SQLAlchemy — the `[postgresql]` extras
   are not needed for DynamoDB-only deployments.

## Migration

See `docs/MIGRATION_DYNAMODB_TO_POSTGRESQL.md` for data migration instructions.

## Alembic Migrations (PostgreSQL only)

```bash
# Set DATABASE_URL or use migration/alembic.ini
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/rfq_engine"

# Run migrations
alembic -c migration/alembic.ini upgrade head

# Rollback one migration
alembic -c migration/alembic.ini downgrade -1

# View migration history
alembic -c migration/alembic.ini history
```

## GraphQL Contract

The GraphQL schema, queries, mutations, and type definitions are identical
for both backends. The repository dispatch boundary (`get_repo()` and
`get_loaders()`) routes to the appropriate backend implementation.