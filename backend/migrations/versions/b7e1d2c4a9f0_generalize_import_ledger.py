"""generalize download_import into a source-agnostic pending_import (§13)

Revision ID: b7e1d2c4a9f0
Revises: 5cc50513cfef
Create Date: 2026-07-17 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1d2c4a9f0"
down_revision: str | None = "5cc50513cfef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("download_import", "pending_import")

    # torrent_hash → source_key (the per-source seen key); recreate its unique index by name
    op.drop_index("ix_download_import_torrent_hash", table_name="pending_import")
    op.alter_column("pending_import", "torrent_hash", new_column_name="source_key")
    op.create_index(
        op.f("ix_pending_import_source_key"), "pending_import", ["source_key"], unique=True
    )

    import_source = sa.Enum("transmission", "watchdir", name="import_source")
    import_source.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "pending_import",
        sa.Column("source", import_source, nullable=False, server_default="transmission"),
    )
    op.alter_column("pending_import", "source", server_default=None)

    op.add_column("pending_import", sa.Column("archive_path", sa.String(), nullable=True))
    op.alter_column("pending_import", "download_dir", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("pending_import", "download_dir", existing_type=sa.String(), nullable=False)
    op.drop_column("pending_import", "archive_path")
    op.drop_column("pending_import", "source")
    sa.Enum(name="import_source").drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_pending_import_source_key"), table_name="pending_import")
    op.alter_column("pending_import", "source_key", new_column_name="torrent_hash")
    op.create_index(
        "ix_download_import_torrent_hash", "pending_import", ["torrent_hash"], unique=True
    )
    op.rename_table("pending_import", "download_import")
