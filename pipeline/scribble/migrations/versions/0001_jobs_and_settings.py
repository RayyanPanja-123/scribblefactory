"""jobs and settings (step 1: were library/.jobs.json and library/settings.json)

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag", sqlmodel.AutoString(), nullable=False),
        sa.Column("slug", sqlmodel.AutoString(), nullable=False),
        sa.Column("part", sqlmodel.AutoString(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("argv", sa.JSON(), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=True),
        sa.Column("status", sqlmodel.AutoString(), nullable=False),
        sa.Column("queued_at", sqlmodel.AutoString(), nullable=True),
        sa.Column("started_at", sqlmodel.AutoString(), nullable=True),
        sa.Column("finished_at", sqlmodel.AutoString(), nullable=True),
        sa.Column("returncode", sa.Integer(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error", sqlmodel.AutoString(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
    )
    op.create_index("ix_job_slug", "job", ["slug"])
    op.create_index("ix_job_status", "job", ["status"])
    op.create_table(
        "setting",
        sa.Column("key", sqlmodel.AutoString(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("setting")
    op.drop_index("ix_job_status", "job")
    op.drop_index("ix_job_slug", "job")
    op.drop_table("job")
