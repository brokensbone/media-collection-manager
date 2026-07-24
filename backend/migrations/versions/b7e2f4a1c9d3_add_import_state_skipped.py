"""add 'skipped' to the import_state enum (import found already in the library, §12/§13)

Revision ID: b7e2f4a1c9d3
Revises: f8a1c2d3e4b5
Create Date: 2026-07-24 16:40:00.000000

When beets finds an import is already in the library it skips it (duplicate_action: skip) rather
than keeping a second copy. That's a no-op, not a failure — record it as `skipped` so the Import
list can say "already in library" instead of showing it as failed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7e2f4a1c9d3"
down_revision: str | None = "6b7c8d9e0f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE import_state ADD VALUE IF NOT EXISTS 'skipped'")


def downgrade() -> None:
    # Postgres has no DROP VALUE; removing an enum value means recreating the type. Forward-only.
    pass
