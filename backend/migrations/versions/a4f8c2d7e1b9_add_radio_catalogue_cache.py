"""add worker-refreshed playable radio catalogue

Revision ID: a4f8c2d7e1b9
Revises: 37e4a66a74e5
Create Date: 2026-09-17 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4f8c2d7e1b9"
down_revision: str | None = "37e4a66a74e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("beets_album_cache", sa.Column("added_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("beets_album_cache", sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE beets_album_cache SET refreshed_at = CURRENT_TIMESTAMP")
    op.alter_column("beets_album_cache", "refreshed_at", nullable=False)
    op.create_table(
        "beets_track_cache",
        sa.Column("item_id", sa.String(), primary_key=True),
        sa.Column("beets_id", sa.String(), sa.ForeignKey("beets_album_cache.beets_id", ondelete="CASCADE"), nullable=False),
        sa.Column("disc", sa.Integer(), nullable=True),
        sa.Column("track", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("path", sa.String(), nullable=False),
    )
    op.create_index("ix_beets_track_cache_beets_id", "beets_track_cache", ["beets_id"])


def downgrade() -> None:
    op.drop_index("ix_beets_track_cache_beets_id", table_name="beets_track_cache")
    op.drop_table("beets_track_cache")
    op.drop_column("beets_album_cache", "refreshed_at")
    op.drop_column("beets_album_cache", "added_at")
