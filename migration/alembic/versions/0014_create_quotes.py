"""Create quotes table

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("quotes"),
        sa.Column("request_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "quote_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "provider_corp_external_id",
            sa.String(255),
            nullable=False,
            server_default="XXXXXXXXXXXXXXXXXXXX",
        ),
        sa.Column("sales_rep_email", sa.String(255), nullable=True),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("shipping_method", sa.String(64), nullable=True),
        sa.Column("shipping_amount", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("total_quote_amount", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("total_quote_discount", sa.Numeric, nullable=False, server_default="0"),
        sa.Column(
            "final_total_quote_amount", sa.Numeric, nullable=False, server_default="0"
        ),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("display_currency", sa.String(8), nullable=True),
        sa.Column("fx_rate", sa.Numeric, nullable=True),
        sa.Column("fx_rate_locked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rounds", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="initial"),
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
        sa.PrimaryKeyConstraint("request_uuid", "quote_uuid"),
    )

    op.create_index(
        prefixed_index("idx_quotes_request_provider_corp_external_id"),
        prefixed_table("quotes"),
        ["request_uuid", "provider_corp_external_id"],
    )
    op.create_index(
        prefixed_index("idx_quotes_request_updated_at"),
        prefixed_table("quotes"),
        ["request_uuid", "updated_at"],
    )
    op.create_index(
        prefixed_index("idx_quotes_provider_corp_external_id_quote_uuid"),
        prefixed_table("quotes"),
        ["provider_corp_external_id", "quote_uuid"],
    )
    op.create_index(
        prefixed_index("idx_quotes_partition_key"),
        prefixed_table("quotes"),
        ["partition_key"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_quotes_partition_key"), table_name=prefixed_table("quotes"))
    op.drop_index(prefixed_index("idx_quotes_provider_corp_external_id_quote_uuid"), table_name=prefixed_table("quotes"))
    op.drop_index(prefixed_index("idx_quotes_request_updated_at"), table_name=prefixed_table("quotes"))
    op.drop_index(prefixed_index("idx_quotes_request_provider_corp_external_id"), table_name=prefixed_table("quotes"))
    op.drop_table(prefixed_table("quotes"))