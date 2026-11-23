"""series, part, cast_member, stage_run (step 3b: were series.json and part.json)

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
S = sqlmodel.AutoString


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", S(), nullable=False),
        sa.Column("title", S(), nullable=False),
        sa.Column("status", S(), nullable=False),
        sa.Column("created_at", S(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("file_text", S(), nullable=True),
    )
    op.create_index("ix_series_slug", "series", ["slug"], unique=True)
    op.create_table(
        "part",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", S(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", S(), nullable=False),
        sa.Column("folder", S(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("series_id", "part_id"),
        sa.UniqueConstraint("series_id", "folder"),
    )
    op.create_index("ix_part_series_id", "part", ["series_id"])
    op.create_table(
        "cast_member",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cast_id", S(), nullable=False),
        sa.Column("name", S(), nullable=False),
        sa.Column("approved_at", S(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("series_id", "cast_id"),
    )
    op.create_index("ix_cast_member_series_id", "cast_member", ["series_id"])
    op.create_table(
        "stage_run",
        sa.Column("part", sa.Integer(), sa.ForeignKey("part.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("stage", S(), primary_key=True),
        sa.Column("status", S(), nullable=False),
        sa.Column("started_at", S(), nullable=True),
        sa.Column("finished_at", S(), nullable=True),
        sa.Column("error", S(), nullable=True),
        sa.Column("inputs_hash", S(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
    )
    op.create_index("ix_stage_run_status", "stage_run", ["status"])


def downgrade() -> None:
    for t in ("stage_run", "cast_member", "part", "series"):
        op.drop_table(t)
