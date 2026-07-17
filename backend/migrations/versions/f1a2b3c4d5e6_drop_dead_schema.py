"""drop dead schema: acquiring/backfill enum values and album.ordered_at

Revision ID: f1a2b3c4d5e6
Revises: d4b8f21c6a30
Create Date: 2026-07-17 17:20:00.000000

The "ordered" acquisition step was dropped from the funnel, leaving the
`acquiring` state, the `backfill` provenance, and the `ordered_at` column
unwritten. Removed here before the first real deploy so they never reach
production. Postgres has no DROP VALUE, so each enum is recreated.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "d4b8f21c6a30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("album", "ordered_at")

    # Fold any rows still carrying a dropped value back onto its live equivalent before the
    # enum loses it (an in-flight `acquiring` album is just `wanted`; `backfill` was a manual
    # seed). A fresh deploy has none of these, but this keeps the migration reusable.
    op.execute("UPDATE album SET state = 'wanted' WHERE state = 'acquiring'")
    op.execute("UPDATE album SET provenance = 'manual' WHERE provenance = 'backfill'")

    op.execute("ALTER TYPE album_state RENAME TO album_state_old")
    op.execute(
        "CREATE TYPE album_state AS ENUM "
        "('suggested', 'saved', 'wanted', 'owned', 'dismissed')"
    )
    op.execute(
        "ALTER TABLE album ALTER COLUMN state TYPE album_state "
        "USING state::text::album_state"
    )
    op.execute("DROP TYPE album_state_old")

    op.execute("ALTER TYPE provenance RENAME TO provenance_old")
    op.execute(
        "CREATE TYPE provenance AS ENUM ('spotify_save', 'artist_watch', 'manual')"
    )
    op.execute(
        "ALTER TABLE album ALTER COLUMN provenance TYPE provenance "
        "USING provenance::text::provenance"
    )
    op.execute("DROP TYPE provenance_old")


def downgrade() -> None:
    # Forward-only: these values were never used, so re-adding them serves no purpose.
    pass
