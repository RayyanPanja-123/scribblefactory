"""cast_uses: which library item each cast member uses (step 3d: "who uses this prop?" in one query)

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
S = sqlmodel.AutoString


def upgrade() -> None:
    op.create_table(
        "cast_uses",
        sa.Column("cast_member", sa.Integer(), sa.ForeignKey("cast_member.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kind", S(), primary_key=True),
        sa.Column("item_id", S(), primary_key=True),
    )
    op.create_index("ix_cast_uses_item", "cast_uses", ["kind", "item_id"])


def downgrade() -> None:
    op.drop_table("cast_uses")
