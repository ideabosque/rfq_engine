"""Create bundles table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("bundles"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "bundle_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("bundle_code", sa.String(128)),
        sa.Column("bundle_name", sa.String(255), nullable=False),
        sa.Column(
            "bundle_type",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'package'"),
        ),
        sa.Column("description", sa.Text),
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
        sa.PrimaryKeyConstraint("partition_key", "bundle_uuid"),
    )

    op.create_index(
        prefixed_index("idx_bundles_partition_bundle_code"),
        prefixed_table("bundles"),
        ["partition_key", "bundle_code"],
    )
    op.create_index(
        prefixed_index("idx_bundles_partition_updated_at"),
        prefixed_table("bundles"),
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_bundles_partition_updated_at"), table_name=prefixed_table("bundles"))
    op.drop_index(prefixed_index("idx_bundles_partition_bundle_code"), table_name=prefixed_table("bundles"))
    op.drop_table(prefixed_table("bundles"))