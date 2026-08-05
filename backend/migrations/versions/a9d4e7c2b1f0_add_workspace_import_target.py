"""add workspace import target

Revision ID: a9d4e7c2b1f0
Revises: f4c1a7b2e9d0
Create Date: 2026-08-05 21:35:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a9d4e7c2b1f0"
down_revision = "f4c1a7b2e9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE media_kind ADD VALUE IF NOT EXISTS 'workspace'")
    op.execute("ALTER TYPE import_target ADD VALUE IF NOT EXISTS 'workspace'")


def downgrade() -> None:
    # PostgreSQL enum values are not safely removable in place.
    pass
