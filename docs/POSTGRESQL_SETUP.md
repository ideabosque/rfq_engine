# PostgreSQL Setup Guide

> Project: `rfq_engine`
> Created: 2026-06-21

## Prerequisites

- PostgreSQL 12+ with the `uuid-ossp` extension
- Python 3.8+

## Installation

```bash
# Install with PostgreSQL support
pip install rfq-engine[postgresql]
```

This installs:
- `SQLAlchemy>=1.4` — ORM and database toolkit
- `psycopg2-binary>=2.9` — PostgreSQL adapter
- `alembic>=1.10` — Database migration tool

## Database Setup

### 1. Create Database and User

```sql
CREATE DATABASE rfq_engine;
CREATE USER rfq WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE rfq_engine TO rfq;

-- Connect to the database and enable uuid-ossp
\c rfq_engine
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### 2. Configure the Engine

Set the following environment variables or pass them in the gateway setting:

```
DB_BACKEND=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_USER=rfq
DB_PASSWORD=your_password
DB_SCHEMA=rfq_engine
```

### 3. Run Migrations

```bash
# From the project root
export DATABASE_URL="postgresql+psycopg2://rfq:your_password@localhost:5432/rfq_engine"
alembic -c migration/alembic.ini upgrade head
```

This creates all 18 entity tables with proper indexes.

### 4. Verify Installation

```bash
# Check tables were created
psql -U rfq -d rfq_engine -c "\dt"
```

You should see tables: `items`, `provider_items`, `provider_item_batches`,
`segments`, `segment_contacts`, `fx_rates`, `cancellation_policies`,
`bundles`, `bundle_components`, `item_catalog_refs`, `item_price_tiers`,
`discount_prompts`, `requests`, `quotes`, `quote_items`, `installments`,
`files`, `availability_holds`.

## Connection Pooling

The SQLAlchemy engine is configured with:
- `pool_size=10` — 10 persistent connections
- `pool_recycle=7200` — recycle connections after 2 hours
- `pool_pre_ping=True` — health-check connections before use
- `echo=False` — set to True for SQL debugging

## Optional AWS Services

When using PostgreSQL backend, AWS services (S3, SQS, Lambda) are optional.
They are initialized only if AWS credentials are provided in the setting.

Without AWS credentials:
- File upload/download features will be unavailable
- S3-based file storage will not work
- SQS/Lambda integrations will not be available

With AWS credentials:
- All features work, but persistence uses PostgreSQL instead of DynamoDB

## Schema Overview

Each table follows these principles:
- **UUID columns** for UUID identifiers
- **String columns** for non-UUID keys (email, file_name, batch_no)
- **JSONB** for flexible structures (MapAttribute, ListAttribute)
- **NUMERIC** for money and quantities
- **TIMESTAMP(timezone=True)** for all timestamps
- **Composite indexes** matching all DynamoDB LSI/GSI access patterns

## Troubleshooting

### "uuid_generate_v4() function does not exist"
Run: `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`

### "psycopg2 import error"
Ensure `psycopg2-binary` is installed: `pip install psycopg2-binary`

### "SQLAlchemy not found"
Install PostgreSQL extras: `pip install rfq-engine[postgresql]`