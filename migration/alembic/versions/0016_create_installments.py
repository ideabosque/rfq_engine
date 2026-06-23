"""Create installments table

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("installments"),
        sa.Column("quote_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "installment_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("request_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("salesorder_no", sa.String(128), nullable=True),
        sa.Column("payment_method", sa.String(64), nullable=False),
        sa.Column("scheduled_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("installment_ratio", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("installment_amount", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
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
        sa.PrimaryKeyConstraint("quote_uuid", "installment_uuid"),
    )

    op.create_index(
        prefixed_index("idx_installments_quote_updated_at"),
        prefixed_table("installments"),
        ["quote_uuid", "updated_at"],
    )
    op.create_index(
        prefixed_index("idx_installments_partition_key"),
        prefixed_table("installments"),
        ["partition_key"],
    )
    op.create_index(
        prefixed_index("idx_installments_request_uuid"),
        prefixed_table("installments"),
        ["request_uuid"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_installments_request_uuid"), table_name=prefixed_table("installments"))
    op.drop_index(prefixed_index("idx_installments_partition_key"), table_name=prefixed_table("installments"))
    op.drop_index(prefixed_index("idx_installments_quote_updated_at"), table_name=prefixed_table("installments"))
    op.drop_table(prefixed_table("installments"))