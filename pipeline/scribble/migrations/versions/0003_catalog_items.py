"""catalog_item: the six shared catalogs (step 2: were library/<kind>.json)

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sqlmodel.AutoString(), nullable=False),
        sa.Column("item_id", sqlmodel.AutoString(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("kind", "item_id"),
    )
    op.create_index("ix_catalog_item_kind", "catalog_item", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_catalog_item_kind", "catalog_item")
    op.drop_table("catalog_item")
