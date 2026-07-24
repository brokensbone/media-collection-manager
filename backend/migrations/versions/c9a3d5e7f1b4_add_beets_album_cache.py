"""add beets_album_cache (worker-refreshed catalogue so the API never runs beet, §5)

Revision ID: c9a3d5e7f1b4
Revises: b7e2f4a1c9d3
Create Date: 2026-07-24 17:10:00.000000

The Owned view and dashboard owned-count used to run a live `beet list` on every page load
(slow, and an API-side reader contending with the worker's `beet import` on the library's SQLite
lock). The worker now caches the catalogue here — refreshed each reconcile and after an import —
and the API reads only this table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9a3d5e7f1b4"
down_revision: str | None = "b7e2f4a1c9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beets_album_cache",
        sa.Column("beets_id", sa.String(), primary_key=True),
        sa.Column("artist", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("mb_releasegroup_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_beets_album_cache_mb_releasegroup_id", "beets_album_cache", ["mb_releasegroup_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_beets_album_cache_mb_releasegroup_id", table_name="beets_album_cache")
    op.drop_table("beets_album_cache")
