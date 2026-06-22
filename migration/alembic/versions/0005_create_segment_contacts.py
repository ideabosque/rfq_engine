"""Create segment_contacts table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "segment_contacts",
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("segment_uuid", UUID(as_uuid=True)),
        sa.Column("contact_uuid", UUID(as_uuid=True)),
        sa.Column(
            "consumer_corp_external_id",
            sa.String(255),
            nullable=False,
            server_default=sa.text("'XXXXXXXXXXXXXXXXXXXX'"),
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
        sa.PrimaryKeyConstraint("partition_key", "email"),
    )

    op.create_index(
        "idx_segment_contacts_partition_consumer_corp",
        "segment_contacts",
        ["partition_key", "consumer_corp_external_id"],
    )
    op.create_index(
        "idx_segment_contacts_partition_segment_uuid",
        "segment_contacts",
        ["partition_key", "segment_uuid"],
    )
    op.create_index(
        "idx_segment_contacts_partition_updated_at",
        "segment_contacts",
        ["partition_key", "updated_at"],
    )


def downgrade():
    op.drop_index(
        "idx_segment_contacts_partition_updated_at",
        table_name="segment_contacts",
    )
    op.drop_index(
        "idx_segment_contacts_partition_segment_uuid",
        table_name="segment_contacts",
    )
    op.drop_index(
        "idx_segment_contacts_partition_consumer_corp",
        table_name="segment_contacts",
    )
    op.drop_table("segment_contacts")