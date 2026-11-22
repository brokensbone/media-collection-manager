"""Store Spotify release years for the Decide queue."""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("album", sa.Column("release_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("album", "release_year")
