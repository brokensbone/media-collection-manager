"""add job_run heartbeat table (§16)

Revision ID: c3a9f1e05b24
Revises: b7e1d2c4a9f0
Create Date: 2026-07-17 11:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a9f1e05b24"
down_revision: str | None = "b7e1d2c4a9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_run",
        sa.Column("job", sa.String(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("job"),
    )


def downgrade() -> None:
    op.drop_table("job_run")
