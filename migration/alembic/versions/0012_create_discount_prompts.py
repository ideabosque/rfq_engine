"""Create discount_prompts table

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from rfq_engine.models.postgresql.base import prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("discount_prompts"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column(
            "discount_prompt_uuid",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("discount_prompt", sa.Text, nullable=False),
        sa.Column("conditions", JSONB, nullable=True),
        sa.Column("discount_rules", JSONB, nullable=True),
        sa.Column("priority", sa.Numeric, nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("partition_key", "discount_prompt_uuid"),
    )

    op.create_index(
        prefixed_index("idx_discount_prompts_partition_scope"),
        prefixed_table("discount_prompts"),
        ["partition_key", "scope"],
    )
    op.create_index(
        prefixed_index("idx_discount_prompts_partition_updated_at"),
        prefixed_table("discount_prompts"),
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(prefixed_index("idx_discount_prompts_partition_updated_at"), table_name=prefixed_table("discount_prompts"))
    op.drop_index(prefixed_index("idx_discount_prompts_partition_scope"), table_name=prefixed_table("discount_prompts"))
    op.drop_table(prefixed_table("discount_prompts"))