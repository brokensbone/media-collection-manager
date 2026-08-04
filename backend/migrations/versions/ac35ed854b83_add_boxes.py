"""add crate boxes + record membership, seed the root Collection (crates §2)

Revision ID: ac35ed854b83
Revises: 63e0b5ebc654
Create Date: 2026-08-04 10:30:00.000000

The crates feature files each owned record into exactly one box in a strict tree. `box` is the
tree (parent_id null = the single root "Collection"); `record_box` maps a beets id to its box.
A record with no record_box row is in the root, so new imports default into Collection without
any hook and the whole library needn't be enumerated at seed time. We seed just the root here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ac35ed854b83"
down_revision: str | None = "63e0b5ebc654"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "box",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("box.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_box_parent_id", "box", ["parent_id"])
    op.create_table(
        "record_box",
        sa.Column("beets_id", sa.String(), primary_key=True),
        sa.Column("box_id", sa.Integer(), sa.ForeignKey("box.id"), nullable=False),
    )
    op.create_index("ix_record_box_box_id", "record_box", ["box_id"])
    op.execute("INSERT INTO box (name, parent_id) VALUES ('Collection', NULL)")


def downgrade() -> None:
    op.drop_index("ix_record_box_box_id", table_name="record_box")
    op.drop_table("record_box")
    op.drop_index("ix_box_parent_id", table_name="box")
    op.drop_table("box")
