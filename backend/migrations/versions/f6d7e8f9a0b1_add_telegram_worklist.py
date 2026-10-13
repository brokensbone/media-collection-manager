"""add Telegram worklist cursor and offer tokens

Revision ID: f6d7e8f9a0b1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-21 19:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6d7e8f9a0b1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_worklist_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("update_offset", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "telegram_worklist_offer",
        sa.Column("token", sa.String(), primary_key=True),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_telegram_worklist_offer_chat_id", "telegram_worklist_offer", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_worklist_offer_chat_id", table_name="telegram_worklist_offer")
    op.drop_table("telegram_worklist_offer")
    op.drop_table("telegram_worklist_state")
