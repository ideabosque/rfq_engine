"""Create segments table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("segments"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "segment_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column(
            "provider_corp_external_id",
            sa.String(255),
            nullable=False,
            server_default=sa.text("'XXXXXXXXXXXXXXXXXXXX'"),
        ),
        sa.Column("segment_name", sa.String(255), nullable=False),
        sa.Column("segment_description", sa.Text),
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
        sa.PrimaryKeyConstraint("partition_key", "segment_uuid"),
    )

    op.create_index(
        prefixed_index("idx_segments_partition_provider_corp"),
        prefixed_table("segments"),
        ["partition_key", "provider_corp_external_id"],
    )
    op.create_index(
        prefixed_index("idx_segments_partition_updated_at"),
        prefixed_table("segments"),
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_segments_partition_updated_at"), table_name=prefixed_table("segments"))
    op.drop_index(prefixed_index("idx_segments_partition_provider_corp"), table_name=prefixed_table("segments"))
    op.drop_table(prefixed_table("segments"))