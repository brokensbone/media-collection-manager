"""add curation facets to beets_album_cache (crates §1)

Revision ID: 63e0b5ebc654
Revises: f4c1a7b2e9d0
Create Date: 2026-08-04 10:00:00.000000

The crates feature curates the owned library by facets that MusicBrainz already carries. Widen
the cached catalogue to surface year, format (media), label, country, secondary types and genre
alongside the release-group id, so the worker's refresh persists them and the API can read them
without a live `beet` call. Read-only for now (slice 1) — nothing splits on them yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "63e0b5ebc654"
down_revision: str | None = "f4c1a7b2e9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("media", "label", "country", "secondary_types", "genre")


def upgrade() -> None:
    op.add_column("beets_album_cache", sa.Column("year", sa.Integer(), nullable=True))
    for name in _COLUMNS:
        op.add_column("beets_album_cache", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in _COLUMNS:
        op.drop_column("beets_album_cache", name)
    op.drop_column("beets_album_cache", "year")
