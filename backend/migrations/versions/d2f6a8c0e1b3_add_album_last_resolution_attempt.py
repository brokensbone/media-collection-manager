"""add album last_resolution_attempt

Revision ID: d2f6a8c0e1b3
Revises: 9c4d7e1f2a3b
Create Date: 2026-07-27 13:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f6a8c0e1b3"
down_revision: str | None = "9c4d7e1f2a3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "album",
        sa.Column("last_resolution_attempt", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("album", "last_resolution_attempt")
