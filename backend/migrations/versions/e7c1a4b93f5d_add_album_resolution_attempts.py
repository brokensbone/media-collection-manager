"""add album.resolution_attempts (§5 fair, least-tried-first resolution order)

Revision ID: e7c1a4b93f5d
Revises: c3e5a7b9d1f2
Create Date: 2026-07-22 12:00:00.000000

Resolution processes a capped batch per run ordered by id, so the low-id MB-absent tail clogged
the front of the queue and starved every album past the cap (they were never even attempted).
Counting attempts lets resolution run least-tried-first: fresh albums go first and the dead tail
sinks. Existing rows start at 0, so they're all treated as freshly eligible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7c1a4b93f5d"
down_revision: str | None = "c3e5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "album",
        sa.Column("resolution_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("album", "resolution_attempts")
