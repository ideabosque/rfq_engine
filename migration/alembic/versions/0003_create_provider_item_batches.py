"""Create provider_item_batches table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_item_batches",
        sa.Column(
            "provider_item_uuid",
            UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("item_uuid", UUID(as_uuid=True)),
        sa.Column("partition_key", sa.String(128)),
        sa.Column("expired_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("produced_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("service_start_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("service_end_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("cost_per_uom", sa.Numeric(18, 6)),
        sa.Column("freight_cost_per_uom", sa.Numeric(18, 6)),
        sa.Column("additional_cost_per_uom", sa.Numeric(18, 6)),
        sa.Column("total_cost_per_uom", sa.Numeric(18, 6)),
        sa.Column(
            "guardrail_margin_per_uom",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("guardrail_price_per_uom", sa.Numeric(18, 6)),
        sa.Column(
            "slow_move_item",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "in_stock",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("availability_qty", sa.Numeric(18, 6)),
        sa.Column("currency", sa.String(16)),
        sa.Column("cancellation_policy_uuid", UUID(as_uuid=True)),
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
        sa.PrimaryKeyConstraint("provider_item_uuid", "batch_no"),
    )

    op.create_index(
        "idx_provider_item_batches_piu_item_uuid",
        "provider_item_batches",
        ["provider_item_uuid", "item_uuid"],
    )
    op.create_index(
        "idx_provider_item_batches_piu_updated_at",
        "provider_item_batches",
        ["provider_item_uuid", "updated_at"],
    )
    op.create_index(
        "idx_provider_item_batches_partition_key",
        "provider_item_batches",
        ["partition_key"],
    )


def downgrade():
    op.drop_index(
        "idx_provider_item_batches_partition_key",
        table_name="provider_item_batches",
    )
    op.drop_index(
        "idx_provider_item_batches_piu_updated_at",
        table_name="provider_item_batches",
    )
    op.drop_index(
        "idx_provider_item_batches_piu_item_uuid",
        table_name="provider_item_batches",
    )
    op.drop_table("provider_item_batches")