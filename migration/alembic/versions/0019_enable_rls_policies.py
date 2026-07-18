"""Enable Row-Level Security policies on all partition-keyed tables.

All RFQ PostgreSQL tables carry a ``partition_key`` column, so every table
gets a tenant-isolation policy.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-16

"""
from alembic import op

from rfq_engine.models.postgresql.base import prefixed_table

# revision identifiers, used by Alembic.
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

RLS_TABLES = [
    "items",
    "provider_items",
    "provider_item_batches",
    "segments",
    "segment_contacts",
    "fx_rates",
    "cancellation_policies",
    "bundles",
    "bundle_components",
    "item_catalog_refs",
    "item_price_tiers",
    "discount_prompts",
    "requests",
    "quotes",
    "quote_items",
    "installments",
    "files",
    "availability_holds",
]


def upgrade():
    for table in RLS_TABLES:
        full_name = prefixed_table(table)
        op.execute(f"ALTER TABLE {full_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {full_name} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {full_name}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {full_name} "
            f"USING (partition_key = current_setting('app.tenant_id', true))"
        )


def downgrade():
    for table in RLS_TABLES:
        full_name = prefixed_table(table)
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {full_name}")
        op.execute(f"ALTER TABLE {full_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {full_name} DISABLE ROW LEVEL SECURITY")
