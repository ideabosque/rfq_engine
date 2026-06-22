"""Create fx_rates table

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fx_rates",
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "fx_rate_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("source_currency", sa.String(8), nullable=False),
        sa.Column("target_currency", sa.String(8), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency_pair_date", sa.String(32), nullable=False),
        sa.Column("rate_date", sa.TIMESTAMP(timezone=True)),
        sa.Column("provider", sa.String(128)),
        sa.Column("notes", sa.Text),
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
        sa.PrimaryKeyConstraint("partition_key", "fx_rate_uuid"),
    )

    op.create_index(
        "idx_fx_rates_partition_currency_pair_date",
        "fx_rates",
        ["partition_key", "currency_pair_date"],
    )
    op.create_index(
        "idx_fx_rates_partition_updated_at",
        "fx_rates",
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index("idx_fx_rates_partition_updated_at", table_name="fx_rates")
    op.drop_index("idx_fx_rates_partition_currency_pair_date", table_name="fx_rates")
    op.drop_table("fx_rates")