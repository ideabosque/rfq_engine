"""Create requests table

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("requests"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "request_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("request_title", sa.String(255), nullable=False),
        sa.Column("request_description", sa.Text, nullable=True),
        sa.Column("billing_address", JSONB, nullable=True),
        sa.Column("shipping_address", JSONB, nullable=True),
        sa.Column("items", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("bundle_uuid", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="initial"),
        sa.Column("expired_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("partition_key", "request_uuid"),
    )

    op.create_index(
        prefixed_index("idx_requests_partition_email"),
        prefixed_table("requests"),
        ["partition_key", "email"],
    )
    op.create_index(
        prefixed_index("idx_requests_partition_updated_at"),
        prefixed_table("requests"),
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_requests_partition_updated_at"), table_name=prefixed_table("requests"))
    op.drop_index(prefixed_index("idx_requests_partition_email"), table_name=prefixed_table("requests"))
    op.drop_table(prefixed_table("requests"))