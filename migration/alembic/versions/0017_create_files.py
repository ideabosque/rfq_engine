"""Create files table

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "files",
        sa.Column("request_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("partition_key", sa.String(128), nullable=False),
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
        sa.PrimaryKeyConstraint("request_uuid", "file_name"),
    )

    op.create_index(
        "idx_files_request_email",
        "files",
        ["request_uuid", "email"],
    )
    op.create_index(
        "idx_files_request_updated_at",
        "files",
        ["request_uuid", "updated_at"],
    )
    op.create_index(
        "idx_files_partition_key",
        "files",
        ["partition_key"],
    )


def downgrade():
    op.drop_index("idx_files_partition_key", table_name="files")
    op.drop_index("idx_files_request_updated_at", table_name="files")
    op.drop_index("idx_files_request_email", table_name="files")
    op.drop_table("files")