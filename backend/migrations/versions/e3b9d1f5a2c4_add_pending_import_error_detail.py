"""add pending_import error_detail

Revision ID: e3b9d1f5a2c4
Revises: d2f6a8c0e1b3
Create Date: 2026-07-27 14:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b9d1f5a2c4"
down_revision: str | None = "d2f6a8c0e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pending_import", sa.Column("error_detail", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_import", "error_detail")
