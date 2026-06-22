"""Create item_catalog_refs table

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "item_catalog_refs",
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "catalog_ref_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "namespace",
            sa.String(128),
            nullable=False,
            server_default=sa.text("'DEFAULT'"),
        ),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("namespace_node_key", sa.String(512), nullable=False),
        sa.Column("extra", JSONB),
        sa.Column("item_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("item_lookup_key", sa.String(255), nullable=False),
        sa.Column("provider_item_uuid", UUID(as_uuid=True)),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'active'"),
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
        sa.PrimaryKeyConstraint("partition_key", "catalog_ref_uuid"),
    )

    op.create_index(
        "idx_item_catalog_refs_partition_namespace_node_key",
        "item_catalog_refs",
        ["partition_key", "namespace_node_key"],
    )
    op.create_index(
        "idx_item_catalog_refs_partition_item_lookup_key",
        "item_catalog_refs",
        ["partition_key", "item_lookup_key"],
    )
    op.create_index(
        "idx_item_catalog_refs_partition_updated_at",
        "item_catalog_refs",
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(
        "idx_item_catalog_refs_partition_updated_at",
        table_name="item_catalog_refs",
    )
    op.drop_index(
        "idx_item_catalog_refs_partition_item_lookup_key",
        table_name="item_catalog_refs",
    )
    op.drop_index(
        "idx_item_catalog_refs_partition_namespace_node_key",
        table_name="item_catalog_refs",
    )
    op.drop_table("item_catalog_refs")