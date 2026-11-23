"""stored_file: every file of a series folder with its size, type, duration and sha256 (step 3c)

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
S = sqlmodel.AutoString


def upgrade() -> None:
    op.create_table(
        "stored_file",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("part.id", ondelete="CASCADE"), nullable=True),
        sa.Column("path", S(), nullable=False),
        sa.Column("filename", S(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", S(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("sha256", S(), nullable=False),
        sa.Column("created_at", S(), nullable=False),
        sa.Column("updated_at", S(), nullable=False),
        sa.UniqueConstraint("path", "filename"),
    )
    op.create_index("ix_stored_file_series_id", "stored_file", ["series_id"])
    op.create_index("ix_stored_file_part_id", "stored_file", ["part_id"])


def downgrade() -> None:
    op.drop_table("stored_file")
