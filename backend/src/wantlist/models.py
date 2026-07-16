from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    LargeBinary,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AlbumState(StrEnum):
    """The funnel (SPEC §4). `owned` is derived by reconcile; the rest are set."""

    suggested = "suggested"
    saved = "saved"
    wanted = "wanted"
    acquiring = "acquiring"
    owned = "owned"
    dismissed = "dismissed"


class Provenance(StrEnum):
    spotify_save = "spotify_save"
    artist_watch = "artist_watch"
    backfill = "backfill"
    manual = "manual"


class LinkSource(StrEnum):
    """How an album's ownership link was set (SPEC §4)."""

    auto = "auto"  # derived by reconcile from a release-group match
    manual = "manual"  # a sticky hand-made link to a beets album


class Album(Base):
    __tablename__ = "album"

    id: Mapped[int] = mapped_column(primary_key=True)
    spotify_id: Mapped[str | None] = mapped_column(unique=True, index=True)
    mb_releasegroup_id: Mapped[str | None] = mapped_column(index=True)
    artist: Mapped[str]
    artist_id: Mapped[str | None] = mapped_column(index=True, default=None)  # primary artist (§6b)
    title: Mapped[str]
    upc: Mapped[str | None] = mapped_column(default=None)
    art_url: Mapped[str | None] = mapped_column(default=None)  # source URL; blob in album_art

    state: Mapped[AlbumState] = mapped_column(SAEnum(AlbumState, name="album_state"))
    provenance: Mapped[Provenance] = mapped_column(SAEnum(Provenance, name="provenance"))

    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    owned_beets_id: Mapped[str | None] = mapped_column(default=None)
    owned_link_source: Mapped[LinkSource | None] = mapped_column(
        SAEnum(LinkSource, name="link_source"), default=None
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlayHistory(Base):
    """A local scrobble log accumulated by polling recently-played (SPEC §4a)."""

    __tablename__ = "play_history"
    __table_args__ = (UniqueConstraint("spotify_track_id", "played_at", name="uq_play"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    spotify_track_id: Mapped[str] = mapped_column(index=True)
    spotify_album_id: Mapped[str | None] = mapped_column(index=True, default=None)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AlbumArt(Base):
    """Owned cover art as a blob (SPEC §4b)."""

    __tablename__ = "album_art"

    album_id: Mapped[int] = mapped_column(
        ForeignKey("album.id", ondelete="CASCADE"), primary_key=True
    )
    content_type: Mapped[str]
    image: Mapped[bytes] = mapped_column(LargeBinary)
    size: Mapped[int]
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SeenRelease(Base):
    """Every album the artist-watch has already accounted for (SPEC §6b). On an artist's
    FIRST watch the whole catalogue is recorded here (baseline) and nothing is surfaced;
    later runs surface only album ids not yet seen — i.e. genuinely new releases."""

    __tablename__ = "seen_release"

    spotify_album_id: Mapped[str] = mapped_column(primary_key=True)
    artist_id: Mapped[str] = mapped_column(index=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationState(Base):
    """Single-row dedup flags so alerts (§8d) fire once per episode, not every poll."""

    __tablename__ = "notification_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    reauth_notified: Mapped[bool] = mapped_column(default=False)
    triage_notified: Mapped[bool] = mapped_column(default=False)


class SpotifyAuth(Base):
    """Single-row token store incl. authorized_at for the 6-month re-auth (SPEC §8c)."""

    __tablename__ = "spotify_auth"

    id: Mapped[int] = mapped_column(primary_key=True)
    access_token: Mapped[str | None] = mapped_column(default=None)
    refresh_token: Mapped[str | None] = mapped_column(default=None)
    access_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    scopes: Mapped[str | None] = mapped_column(default=None)
