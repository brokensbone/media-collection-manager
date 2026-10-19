"""add independent radio Navidrome destinations

Revision ID: a6b7c8d9e0f1
Revises: f6d7e8f9a0b1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radio_navidrome_sync",
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("radio_schedule.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("playlist_id", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("unmatched_paths", sa.JSON(), nullable=False),
        sa.Column("track_count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("radio_navidrome_sync")
