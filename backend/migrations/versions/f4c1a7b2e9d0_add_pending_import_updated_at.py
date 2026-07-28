"""add pending_import updated_at

Revision ID: f4c1a7b2e9d0
Revises: e3b9d1f5a2c4
Create Date: 2026-07-27 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4c1a7b2e9d0"
down_revision: str | None = "e3b9d1f5a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pending_import",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_import", "updated_at")
