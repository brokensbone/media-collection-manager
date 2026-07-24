from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
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
    owned = "owned"
    dismissed = "dismissed"


class Provenance(StrEnum):
    spotify_save = "spotify_save"
    artist_watch = "artist_watch"
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

    # Failed resolution attempts (§5). Resolution runs least-tried-first, so the MB-absent tail
    # sinks below fresh albums instead of clogging the front of the queue and starving them.
    resolution_attempts: Mapped[int] = mapped_column(default=0, server_default="0")

    state: Mapped[AlbumState] = mapped_column(SAEnum(AlbumState, name="album_state"))
    provenance: Mapped[Provenance] = mapped_column(SAEnum(Provenance, name="provenance"))

    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
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


class ImportState(StrEnum):
    detected = "detected"  # awaiting the operator's Import click
    queued = "queued"  # clicked; awaiting background processing by the worker
    importing = "importing"  # the worker is actively staging/importing this one right now
    imported = "imported"
    skipped = "skipped"  # beets found it already in the library — no second copy kept (§12/§13)
    failed = "failed"
    dismissed = "dismissed"  # operator discarded it; kept so its source-key stays in the ledger


class ImportSource(StrEnum):
    """Which front surfaced this import (SPEC §12/§13). They share the import → beets →
    reconcile tail; only the staging step differs (rsync pull vs. local unpack)."""

    transmission = "transmission"
    watchdir = "watchdir"


class PendingImport(Base):
    """An acquisition awaiting a one-click import into beets, from either front (§12/§13).
    `source_key` is the per-source seen-ledger key (torrent hash / drop path) so a given
    acquisition is only ever processed once."""

    __tablename__ = "pending_import"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[ImportSource] = mapped_column(SAEnum(ImportSource, name="import_source"))
    source_key: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    download_dir: Mapped[str | None] = mapped_column(default=None)  # §12 transfer source
    files: Mapped[list[str]] = mapped_column(JSON, default=list)  # §12 paths relative to dir
    archive_path: Mapped[str | None] = mapped_column(default=None)  # §13 zip/folder to unpack
    matched_album_id: Mapped[int | None] = mapped_column(
        ForeignKey("album.id", ondelete="SET NULL"), default=None
    )
    state: Mapped[ImportState] = mapped_column(
        SAEnum(ImportState, name="import_state"), default=ImportState.detected
    )
    # Whether the download contains audio (§12 non-music filter). None = not screened (watch-dir
    # drops, older rows). Kept even for skipped torrents so the Transmission page can show them.
    has_audio: Mapped[bool | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRun(Base):
    """Per-poller heartbeat (SPEC §16, D18). Each scheduled job records its last run/success/
    error to the DB so `/metrics` (served by the *API* process) can see the *worker* process's
    liveness — in-process counters wouldn't cross the process boundary. Alerts on staleness."""

    __tablename__ = "job_run"

    job: Mapped[str] = mapped_column(primary_key=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    runs: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)


class WorkerEvent(Base):
    """Append-only activity log the worker writes as it processes items (resolve, own, import,
    …). The Activity view (served by the *API* process) tails it, so — like job_run — it goes
    through the DB because the worker's in-memory state can't cross the process boundary. Pruned
    to a recent window; `id` is the poll cursor."""

    __tablename__ = "worker_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    job: Mapped[str]  # which poller: resolution, reconcile, ingest, import, watchdir, …
    type: Mapped[str]  # machine tag for the UI: resolved, no_match, owned, imported, error, …
    message: Mapped[str]
    album_id: Mapped[int | None] = mapped_column(
        ForeignKey("album.id", ondelete="SET NULL"), default=None
    )


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
