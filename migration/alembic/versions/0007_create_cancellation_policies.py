"""Create cancellation_policies table

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cancellation_policies",
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "policy_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("provider_item_uuid", UUID(as_uuid=True)),
        sa.Column("label", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("tiers", JSONB),
        sa.Column("notes_template_uuid", UUID(as_uuid=True)),
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
        sa.PrimaryKeyConstraint("partition_key", "policy_uuid"),
    )

    op.create_index(
        "idx_cancellation_policies_partition_provider_item_uuid",
        "cancellation_policies",
        ["partition_key", "provider_item_uuid"],
    )
    op.create_index(
        "idx_cancellation_policies_partition_updated_at",
        "cancellation_policies",
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(
        "idx_cancellation_policies_partition_updated_at",
        table_name="cancellation_policies",
    )
    op.drop_index(
        "idx_cancellation_policies_partition_provider_item_uuid",
        table_name="cancellation_policies",
    )
    op.drop_table("cancellation_policies")