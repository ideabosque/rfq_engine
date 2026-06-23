"""Create item_price_tiers table

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("item_price_tiers"),
        sa.Column("item_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "item_price_tier_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("provider_item_uuid", UUID(as_uuid=True)),
        sa.Column("segment_uuid", UUID(as_uuid=True)),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("quantity_greater_then", sa.Numeric, nullable=False),
        sa.Column("quantity_less_then", sa.Numeric, nullable=True),
        sa.Column("pax_type", sa.String(64), nullable=True),
        sa.Column("margin_per_uom", sa.Numeric, nullable=True),
        sa.Column("price_per_uom", sa.Numeric, nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("base_occupancy", JSONB, nullable=True),
        sa.Column("extra_pax_surcharges", JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_review"),
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
        sa.PrimaryKeyConstraint("item_uuid", "item_price_tier_uuid"),
    )

    op.create_index(
        prefixed_index("idx_item_price_tiers_item_provider_item_uuid"),
        prefixed_table("item_price_tiers"),
        ["item_uuid", "provider_item_uuid"],
    )
    op.create_index(
        prefixed_index("idx_item_price_tiers_item_segment_uuid"),
        prefixed_table("item_price_tiers"),
        ["item_uuid", "segment_uuid"],
    )
    op.create_index(
        prefixed_index("idx_item_price_tiers_item_updated_at"),
        prefixed_table("item_price_tiers"),
        ["item_uuid", "updated_at"],
    )
    op.create_index(
        prefixed_index("idx_item_price_tiers_partition_key"),
        prefixed_table("item_price_tiers"),
        ["partition_key"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_item_price_tiers_partition_key"), table_name=prefixed_table("item_price_tiers"))
    op.drop_index(prefixed_index("idx_item_price_tiers_item_updated_at"), table_name=prefixed_table("item_price_tiers"))
    op.drop_index(prefixed_index("idx_item_price_tiers_item_segment_uuid"), table_name=prefixed_table("item_price_tiers"))
    op.drop_index(prefixed_index("idx_item_price_tiers_item_provider_item_uuid"), table_name=prefixed_table("item_price_tiers"))
    op.drop_table(prefixed_table("item_price_tiers"))