"""Create availability_holds table

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "availability_holds",
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "hold_token",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("provider_item_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("quote_uuid", UUID(as_uuid=True), nullable=True),
        sa.Column("quote_item_uuid", UUID(as_uuid=True), nullable=True),
        sa.Column("qty", sa.Numeric, nullable=False),
        sa.Column("service_start_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("service_end_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="held"),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("partition_key", "hold_token"),
    )

    op.create_index(
        "idx_availability_holds_provider_item_uuid",
        "availability_holds",
        ["provider_item_uuid"],
    )
    op.create_index(
        "idx_availability_holds_quote_uuid",
        "availability_holds",
        ["quote_uuid"],
    )
    op.create_index(
        "idx_availability_holds_status",
        "availability_holds",
        ["status"],
    )
    op.create_index(
        "idx_availability_holds_expires_at",
        "availability_holds",
        ["expires_at"],
    )


def downgrade():
    op.drop_index("idx_availability_holds_expires_at", table_name="availability_holds")
    op.drop_index("idx_availability_holds_status", table_name="availability_holds")
    op.drop_index("idx_availability_holds_quote_uuid", table_name="availability_holds")
    op.drop_index(
        "idx_availability_holds_provider_item_uuid", table_name="availability_holds"
    )
    op.drop_table("availability_holds")