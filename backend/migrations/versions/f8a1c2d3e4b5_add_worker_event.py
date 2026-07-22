"""add worker_event (activity feed the worker writes and the API tails)

Revision ID: f8a1c2d3e4b5
Revises: e7c1a4b93f5d
Create Date: 2026-07-22 15:30:00.000000

An append-only log of what the worker is doing at item granularity (resolve/own/import/…), so
the Activity view served by the API process can tail it. Like job_run it lives in the DB because
the worker's state can't cross the process boundary. Pruned to a recent window by the writer.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8a1c2d3e4b5"
down_revision: str | None = "e7c1a4b93f5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("job", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column(
            "album_id",
            sa.Integer(),
            sa.ForeignKey("album.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_worker_event_created_at", "worker_event", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_event_created_at", table_name="worker_event")
    op.drop_table("worker_event")
