"""add pending_import.has_audio (§12 non-music screening record)

Revision ID: b2d4f6a8c0e1
Revises: a1c2e3f4b5d6
Create Date: 2026-07-20 12:20:00.000000

Records whether a detected download contained audio, so the Transmission page can list every
torrent seen — including ones skipped as non-music — and label why they were skipped.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: str | None = "a1c2e3f4b5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pending_import", sa.Column("has_audio", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_import", "has_audio")
