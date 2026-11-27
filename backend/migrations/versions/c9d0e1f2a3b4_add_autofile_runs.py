"""Persist crate autofile inputs, decisions and accept/dismiss outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autofile_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("beets_id", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_box_id", sa.Integer(), nullable=False),
        sa.Column("destination_box_id", sa.Integer(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        *[
            sa.Column(name, sa.JSON(), nullable=False)
            for name in ("album", "evidence", "request", "response", "result")
        ],
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_autofile_run_beets_id", "autofile_run", ["beets_id"])
    op.create_index("ix_autofile_run_status", "autofile_run", ["status"])


def downgrade() -> None:
    op.drop_table("autofile_run")
