"""add 'importing' to the import_state enum (active-import progress, §12/§13)

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-07-20 15:20:00.000000

The worker marks the import it's actively processing as `importing` (queued -> importing ->
imported/failed) so the UI can show which one is running versus which are still waiting.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c3e5a7b9d1f2"
down_revision: str | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE import_state ADD VALUE IF NOT EXISTS 'importing'")


def downgrade() -> None:
    # Postgres has no DROP VALUE; removing an enum value means recreating the type. Forward-only.
    pass
