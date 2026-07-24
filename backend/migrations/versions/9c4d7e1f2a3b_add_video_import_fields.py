"""add video import fields

Revision ID: 9c4d7e1f2a3b
Revises: b7e1d2c4a9f0
Create Date: 2026-07-24 15:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c4d7e1f2a3b"
down_revision: Union[str, Sequence[str], None] = "b7e1d2c4a9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


media_kind = sa.Enum("music", "tv", "film", "unknown", name="media_kind")
import_target = sa.Enum(
    "beets", "tv", "film", "review", name="import_target"
)


def upgrade() -> None:
    bind = op.get_bind()
    media_kind.create(bind, checkfirst=True)
    import_target.create(bind, checkfirst=True)

    op.add_column(
        "pending_import",
        sa.Column(
            "media_kind",
            media_kind,
            nullable=False,
            server_default="music",
        ),
    )
    op.add_column(
        "pending_import",
        sa.Column(
            "import_target",
            import_target,
            nullable=False,
            server_default="beets",
        ),
    )
    op.add_column(
        "pending_import", sa.Column("classification_detail", sa.String(), nullable=True)
    )
    op.add_column("pending_import", sa.Column("destination_path", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE pending_import
        SET media_kind = CASE
            WHEN source = 'transmission' AND has_audio IS FALSE THEN 'unknown'::media_kind
            ELSE 'music'::media_kind
        END,
        import_target = CASE
            WHEN source = 'transmission' AND has_audio IS FALSE THEN 'review'::import_target
            ELSE 'beets'::import_target
        END
        """
    )

    op.alter_column("pending_import", "media_kind", server_default=None)
    op.alter_column("pending_import", "import_target", server_default=None)


def downgrade() -> None:
    op.drop_column("pending_import", "destination_path")
    op.drop_column("pending_import", "classification_detail")
    op.drop_column("pending_import", "import_target")
    op.drop_column("pending_import", "media_kind")

    bind = op.get_bind()
    import_target.drop(bind, checkfirst=True)
    media_kind.drop(bind, checkfirst=True)
