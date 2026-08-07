"""add album.album_type

Revision ID: 37e4a66a74e5
Revises: a9d4e7c2b1f0
Create Date: 2026-08-07 11:17:21.966508
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '37e4a66a74e5'
down_revision: str | None = 'a9d4e7c2b1f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('album', sa.Column('album_type', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('album', 'album_type')
