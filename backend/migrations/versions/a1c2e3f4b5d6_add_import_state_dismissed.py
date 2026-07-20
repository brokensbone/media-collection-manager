"""add 'dismissed' to the import_state enum (discard an unwanted import, §12/§13)

Revision ID: a1c2e3f4b5d6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-20 11:40:00.000000

Discarding an import must be sticky: the row is kept (state=dismissed) so its source-key
stays in the seen-ledger and a still-seeding torrent isn't re-detected on the next poll.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a1c2e3f4b5d6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE import_state ADD VALUE IF NOT EXISTS 'dismissed'")


def downgrade() -> None:
    # Postgres has no DROP VALUE; removing an enum value means recreating the type. Forward-only.
    pass
