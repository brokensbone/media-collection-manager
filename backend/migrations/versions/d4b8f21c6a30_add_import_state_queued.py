"""add 'queued' to the import_state enum (async imports, §12/§13)

Revision ID: d4b8f21c6a30
Revises: c3a9f1e05b24
Create Date: 2026-07-17 16:30:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "d4b8f21c6a30"
down_revision: str | None = "c3a9f1e05b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Imports now go detected -> queued -> imported/failed so the worker can process them in
    # the background. Postgres 12+ allows ADD VALUE inside a transaction as long as the new
    # value isn't used in the same transaction (we don't).
    op.execute("ALTER TYPE import_state ADD VALUE IF NOT EXISTS 'queued'")


def downgrade() -> None:
    # Postgres has no DROP VALUE; removing an enum value means recreating the type. Forward-only.
    pass
