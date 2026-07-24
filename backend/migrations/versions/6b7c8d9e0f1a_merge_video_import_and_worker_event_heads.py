"""merge video import and worker_event heads

Revision ID: 6b7c8d9e0f1a
Revises: 9c4d7e1f2a3b, f8a1c2d3e4b5
Create Date: 2026-07-24 15:10:00.000000
"""

from collections.abc import Sequence


revision: str = "6b7c8d9e0f1a"
down_revision: str | Sequence[str] | None = ("9c4d7e1f2a3b", "f8a1c2d3e4b5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
