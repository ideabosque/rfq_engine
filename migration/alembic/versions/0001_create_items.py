"""Create items table

Revision ID: 0001
Revises:
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable uuid_generate_v4() extension if not already enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        prefixed_table("items"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "item_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column("item_type", sa.String(64), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("item_description", sa.Text),
        sa.Column("pricing_mode", sa.String(64)),
        sa.Column("uom", sa.String(64), nullable=False),
        sa.Column("item_external_id", sa.String(255)),
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
        sa.PrimaryKeyConstraint("partition_key", "item_uuid"),
    )

    op.create_index(
        prefixed_index("idx_items_partition_item_type"),
        prefixed_table("items"),
        ["partition_key", "item_type"],
    )
    op.create_index(
        prefixed_index("idx_items_partition_updated_at"),
        prefixed_table("items"),
        ["partition_key", "updated_at"],
    )
    op.create_index(
        prefixed_index("idx_items_partition_external_id"),
        prefixed_table("items"),
        ["partition_key", "item_external_id"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_items_partition_external_id"), table_name=prefixed_table("items"))
    op.drop_index(prefixed_index("idx_items_partition_updated_at"), table_name=prefixed_table("items"))
    op.drop_index(prefixed_index("idx_items_partition_item_type"), table_name=prefixed_table("items"))
    op.drop_table(prefixed_table("items"))