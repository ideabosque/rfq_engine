"""Create quote_items table

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("quote_items"),
        sa.Column("quote_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "quote_item_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("provider_item_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("item_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("batch_no", sa.String(128), nullable=True),
        sa.Column("request_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("request_data", JSONB, nullable=True),
        sa.Column("price_per_uom", sa.Numeric, nullable=False),
        sa.Column("qty", sa.Numeric, nullable=False),
        sa.Column("pax_breakdown", JSONB, nullable=True),
        sa.Column("bundle_uuid", UUID(as_uuid=True), nullable=True),
        sa.Column("bundle_label", sa.String(255), nullable=True),
        sa.Column("bundle_component_uuid", UUID(as_uuid=True), nullable=True),
        sa.Column("subtotal", sa.Numeric, nullable=False),
        sa.Column("subtotal_discount", sa.Numeric, nullable=True),
        sa.Column("final_subtotal", sa.Numeric, nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("subtotal_native", sa.Numeric, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("hold_token", sa.String(128), nullable=True),
        sa.Column("hold_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("quote_uuid", "quote_item_uuid"),
    )

    op.create_index(
        prefixed_index("idx_quote_items_quote_provider_item_uuid"),
        prefixed_table("quote_items"),
        ["quote_uuid", "provider_item_uuid"],
    )
    op.create_index(
        prefixed_index("idx_quote_items_quote_item_uuid"),
        prefixed_table("quote_items"),
        ["quote_uuid", "item_uuid"],
    )
    op.create_index(
        prefixed_index("idx_quote_items_quote_updated_at"),
        prefixed_table("quote_items"),
        ["quote_uuid", "updated_at"],
    )
    op.create_index(
        prefixed_index("idx_quote_items_item_uuid_provider_item_uuid"),
        prefixed_table("quote_items"),
        ["item_uuid", "provider_item_uuid"],
    )
    op.create_index(
        prefixed_index("idx_quote_items_partition_key"),
        prefixed_table("quote_items"),
        ["partition_key"],
    )
    op.create_index(
        prefixed_index("idx_quote_items_request_uuid"),
        prefixed_table("quote_items"),
        ["request_uuid"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_quote_items_request_uuid"), table_name=prefixed_table("quote_items"))
    op.drop_index(prefixed_index("idx_quote_items_partition_key"), table_name=prefixed_table("quote_items"))
    op.drop_index(prefixed_index("idx_quote_items_item_uuid_provider_item_uuid"), table_name=prefixed_table("quote_items"))
    op.drop_index(prefixed_index("idx_quote_items_quote_updated_at"), table_name=prefixed_table("quote_items"))
    op.drop_index(prefixed_index("idx_quote_items_quote_item_uuid"), table_name=prefixed_table("quote_items"))
    op.drop_index(prefixed_index("idx_quote_items_quote_provider_item_uuid"), table_name=prefixed_table("quote_items"))
    op.drop_table(prefixed_table("quote_items"))