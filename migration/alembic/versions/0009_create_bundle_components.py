"""Create bundle_components table

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("bundle_components"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "bundle_component_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("bundle_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("item_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("provider_item_uuid", UUID(as_uuid=True)),
        sa.Column("component_role", sa.String(64)),
        sa.Column(
            "required",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("default_qty", sa.Numeric(18, 4)),
        sa.Column("sort_order", sa.Numeric(18, 4)),
        sa.Column("extra", JSONB),
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
        sa.PrimaryKeyConstraint("partition_key", "bundle_component_uuid"),
    )

    op.create_index(
        prefixed_index("idx_bundle_components_partition_bundle_uuid"),
        prefixed_table("bundle_components"),
        ["partition_key", "bundle_uuid"],
    )
    op.create_index(
        prefixed_index("idx_bundle_components_partition_updated_at"),
        prefixed_table("bundle_components"),
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(
        "idx_bundle_components_partition_updated_at",
        table_name="bundle_components",
    )
    op.drop_index(
        "idx_bundle_components_partition_bundle_uuid",
        table_name="bundle_components",
    )
    op.drop_table(prefixed_table("bundle_components"))