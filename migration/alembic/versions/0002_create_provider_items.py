"""Create provider_items table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_items",
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "provider_item_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("item_uuid", UUID(as_uuid=True)),
        sa.Column(
            "provider_corp_external_id",
            sa.String(255),
            nullable=False,
            server_default=sa.text("'XXXXXXXXXXXXXXXXXXXX'"),
        ),
        sa.Column("provider_item_external_id", sa.String(255)),
        sa.Column("base_price_per_uom", sa.Numeric(18, 6)),
        sa.Column("item_spec", JSONB),
        sa.Column(
            "availability_mode",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("partition_key", "provider_item_uuid"),
    )

    op.create_index(
        "idx_provider_items_partition_item_uuid",
        "provider_items",
        ["partition_key", "item_uuid"],
    )
    op.create_index(
        "idx_provider_items_partition_provider_corp",
        "provider_items",
        ["partition_key", "provider_corp_external_id"],
    )
    op.create_index(
        "idx_provider_items_partition_external_id",
        "provider_items",
        ["partition_key", "provider_item_external_id"],
    )
    op.create_index(
        "idx_provider_items_partition_updated_at",
        "provider_items",
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(
        "idx_provider_items_partition_updated_at", table_name="provider_items"
    )
    op.drop_index(
        "idx_provider_items_partition_external_id",
        table_name="provider_items",
    )
    op.drop_index(
        "idx_provider_items_partition_provider_corp",
        table_name="provider_items",
    )
    op.drop_index(
        "idx_provider_items_partition_item_uuid", table_name="provider_items"
    )
    op.drop_table("provider_items")