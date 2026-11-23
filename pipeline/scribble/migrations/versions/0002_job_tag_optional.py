"""job.tag may be empty: jobs from before tags existed (api/jobs.load_jobs derives theirs after loading)

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlmodel

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("job") as b:
        b.alter_column("tag", existing_type=sqlmodel.AutoString(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("job") as b:
        b.alter_column("tag", existing_type=sqlmodel.AutoString(), nullable=False)
