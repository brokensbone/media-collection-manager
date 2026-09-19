"""add radio schedules

Revision ID: d5e6f7a8b9c0
Revises: a4f8c2d7e1b9
Create Date: 2026-09-19 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "a4f8c2d7e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radio_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("schedule_date"),
    )
    op.create_index("ix_radio_schedule_schedule_date", "radio_schedule", ["schedule_date"])
    op.create_table(
        "radio_schedule_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("radio_schedule.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("starts_at", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
    )
    op.create_index("ix_radio_schedule_session_schedule_id", "radio_schedule_session", ["schedule_id"])
    op.create_table(
        "radio_schedule_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("radio_schedule_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("beets_id", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
    )
    op.create_index("ix_radio_schedule_item_session_id", "radio_schedule_item", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_radio_schedule_item_session_id", table_name="radio_schedule_item")
    op.drop_table("radio_schedule_item")
    op.drop_index("ix_radio_schedule_session_schedule_id", table_name="radio_schedule_session")
    op.drop_table("radio_schedule_session")
    op.drop_index("ix_radio_schedule_schedule_date", table_name="radio_schedule")
    op.drop_table("radio_schedule")
