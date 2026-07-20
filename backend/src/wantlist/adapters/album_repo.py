from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from ..domain.verdict import PlayStat
from ..models import (
    Album,
    AlbumArt,
    AlbumState,
    ImportSource,
    ImportState,
    JobRun,
    LinkSource,
    NotificationState,
    PendingImport,
    PlayHistory,
    Provenance,
    SeenRelease,
)
from ..ports.spotify_api import Play


@dataclass
class UnresolvedAlbum:
    id: int
    spotify_id: str | None
    upc: str | None
    artist: str
    title: str


@dataclass
class AlbumSummary:
    id: int
    artist: str
    title: str
    state: str
    mb_releasegroup_id: str | None
    owned: bool
    has_art: bool


@dataclass
class SavedCandidate:
    id: int
    spotify_id: str | None
    artist: str
    title: str
    saved_at: datetime | None
    has_art: bool


@dataclass
class AcquireRow:
    id: int
    artist: str
    title: str
    has_art: bool


@dataclass
class SuggestedRow:
    id: int
    artist: str
    title: str
    has_art: bool


@dataclass
class WantedForMatch:
    id: int
    artist: str
    title: str


@dataclass
class ImportRow:
    id: int
    source: str
    name: str
    state: str
    matched_album_id: int | None
    matched_artist: str | None
    matched_title: str | None


@dataclass
class ImportRecord:
    id: int
    source: str
    download_dir: str | None
    files: list[str]
    archive_path: str | None
    matched_album_id: int | None
    state: str


@dataclass
class JobRunRow:
    job: str
    last_success_at: datetime | None
    runs: int
    errors: int


class AlbumRepo:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def existing_spotify_ids(self) -> set[str]:
        with self._sf() as session:
            rows = session.scalars(select(Album.spotify_id).where(Album.spotify_id.is_not(None)))
            return {r for r in rows if r is not None}

    def add_saved_album(
        self,
        *,
        spotify_id: str,
        artist: str,
        artist_id: str | None,
        title: str,
        upc: str | None,
        added_at: datetime | None,
        art_url: str | None,
    ) -> None:
        with self._sf() as session:
            session.add(
                Album(
                    spotify_id=spotify_id,
                    artist=artist,
                    artist_id=artist_id,
                    title=title,
                    upc=upc,
                    art_url=art_url,
                    saved_at=added_at,
                    state=AlbumState.saved,
                    provenance=Provenance.spotify_save,
                )
            )
            session.commit()

    def add_suggested_album(
        self,
        *,
        spotify_id: str,
        artist: str,
        artist_id: str | None,
        title: str,
        art_url: str | None,
    ) -> None:
        with self._sf() as session:
            session.add(
                Album(
                    spotify_id=spotify_id,
                    artist=artist,
                    artist_id=artist_id,
                    title=title,
                    art_url=art_url,
                    state=AlbumState.suggested,
                    provenance=Provenance.artist_watch,
                )
            )
            session.commit()

    def kept_artist_ids(self) -> set[str]:
        """Artist ids of albums that survived a keep-verdict — the 6b watch seed (§6b)."""
        kept = (AlbumState.wanted, AlbumState.owned)
        with self._sf() as session:
            rows = session.scalars(
                select(Album.artist_id).where(Album.artist_id.is_not(None), Album.state.in_(kept))
            )
            return {r for r in rows if r is not None}

    def albums_missing_art(self) -> list[tuple[int, str]]:
        """Albums that have a source URL but no stored blob yet."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.art_url)
                .outerjoin(AlbumArt, AlbumArt.album_id == Album.id)
                .where(Album.art_url.is_not(None), AlbumArt.album_id.is_(None))
            )
            return [(album_id, url) for album_id, url in rows if url is not None]

    def save_art(self, album_id: int, content_type: str, data: bytes) -> None:
        with self._sf() as session:
            session.merge(
                AlbumArt(album_id=album_id, content_type=content_type, image=data, size=len(data))
            )
            session.commit()

    def get_art(self, album_id: int) -> tuple[str, bytes] | None:
        with self._sf() as session:
            row = session.get(AlbumArt, album_id)
            return (row.content_type, row.image) if row else None

    # --- resolution (§5) -------------------------------------------------------------

    def albums_needing_resolution(self) -> list[UnresolvedAlbum]:
        """Non-dismissed albums without a release-group id yet (resolve-once, re-try tail)."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.spotify_id, Album.upc, Album.artist, Album.title).where(
                    Album.mb_releasegroup_id.is_(None),
                    Album.state != AlbumState.dismissed,
                )
            )
            return [UnresolvedAlbum(*row) for row in rows]

    def set_release_group(self, album_id: int, mb_releasegroup_id: str) -> None:
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id)
                .values(mb_releasegroup_id=mb_releasegroup_id)
            )
            session.commit()

    # --- ownership reconcile (§5) ----------------------------------------------------

    def resolvable_unowned(self) -> list[tuple[int, str]]:
        """(id, release-group id) for albums that could still auto-resolve to owned:
        have a release-group id, not already owned, and not a manual link (never clobbered)."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.mb_releasegroup_id).where(
                    Album.mb_releasegroup_id.is_not(None),
                    Album.state != AlbumState.owned,
                    Album.owned_link_source.is_distinct_from(LinkSource.manual),
                )
            )
            return [(album_id, rgid) for album_id, rgid in rows]

    def mark_owned_auto(self, album_ids: list[int]) -> None:
        if not album_ids:
            return
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id.in_(album_ids))
                .values(state=AlbumState.owned, owned_link_source=LinkSource.auto)
            )
            session.commit()

    # --- verdict / Decide (§6a) ------------------------------------------------------

    def saved_pending(self, now: datetime) -> list[SavedCandidate]:
        """Saved albums awaiting a verdict and not currently snoozed. Trigger evaluation
        (forgotten/listened) happens in the service against play stats. Oldest first."""
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(
                    Album.id, Album.spotify_id, Album.artist, Album.title, Album.saved_at, has_art
                )
                .where(
                    Album.state == AlbumState.saved,
                    (Album.snoozed_until.is_(None)) | (Album.snoozed_until <= now),
                )
                .order_by(Album.saved_at)
            )
            return [SavedCandidate(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]

    def play_stats_by_album(self) -> dict[str, PlayStat]:
        """Per-Spotify-album play stats from the accumulated play history (§4a)."""
        with self._sf() as session:
            rows = session.execute(
                select(
                    PlayHistory.spotify_album_id,
                    func.count(func.distinct(PlayHistory.spotify_track_id)),
                    func.min(PlayHistory.played_at),
                    func.max(PlayHistory.played_at),
                )
                .where(PlayHistory.spotify_album_id.is_not(None))
                .group_by(PlayHistory.spotify_album_id)
            )
            return {
                r[0]: PlayStat(distinct_tracks=r[1], first_played=r[2], last_played=r[3])
                for r in rows
            }

    def add_plays(self, plays: list[Play]) -> int:
        """Append plays, ignoring ones already recorded (unique on track + played_at)."""
        if not plays:
            return 0
        with self._sf() as session:
            # RETURNING counts rows actually inserted (skipped conflicts aren't returned);
            # psycopg3's rowcount is unreliable (-1) for a multi-row ON CONFLICT insert.
            inserted = session.execute(
                pg_insert(PlayHistory)
                .values(
                    [
                        {
                            "spotify_track_id": p.spotify_track_id,
                            "spotify_album_id": p.spotify_album_id,
                            "played_at": p.played_at,
                        }
                        for p in plays
                    ]
                )
                .on_conflict_do_nothing(constraint="uq_play")
                .returning(PlayHistory.id)
            ).all()
            session.commit()
            return len(inserted)

    def set_verdict(self, album_id: int, state: AlbumState, verdict_at: datetime) -> None:
        """Keep/drop: only a `saved` album can receive a verdict."""
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.saved)
                .values(state=state, verdict_at=verdict_at)
            )
            session.commit()

    def snooze(self, album_id: int, snoozed_until: datetime) -> None:
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.saved)
                .values(snoozed_until=snoozed_until)
            )
            session.commit()

    # --- acquire (§7) ----------------------------------------------------------------

    def acquire_queue(self) -> list[AcquireRow]:
        """`wanted` albums to buy."""
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.id, Album.artist, Album.title, has_art)
                .where(Album.state == AlbumState.wanted)
                .order_by(Album.artist, Album.title)
            )
            return [AcquireRow(r[0], r[1], r[2], r[3]) for r in rows]

    def mark_owned_manual(self, album_id: int, beets_id: str | None) -> None:
        """A sticky manual ownership link (§4/§5) — reconcile never clobbers it. Closes the
        loop for edition mismatches and MB-absent albums."""
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id)
                .values(
                    state=AlbumState.owned,
                    owned_link_source=LinkSource.manual,
                    owned_beets_id=beets_id,
                )
            )
            session.commit()

    def tracked_release_group_ids(self) -> set[str]:
        """Release-group ids already on some album row — so a reverse-matched import (D21)
        doesn't duplicate an album a want already covers (reconcile owns those)."""
        with self._sf() as session:
            rows = session.scalars(
                select(Album.mb_releasegroup_id).where(Album.mb_releasegroup_id.is_not(None))
            )
            return {r for r in rows if r is not None}

    def add_owned_import(
        self,
        *,
        artist: str,
        title: str,
        mb_releasegroup_id: str | None,
        beets_id: str,
        spotify_id: str | None,
        art_url: str | None,
    ) -> None:
        """Record a directly-imported album as owned (D21 reverse-match), so it shows in Owned.
        Sticky manual link (reconcile never clobbers it); art back-fills via the art job. If the
        spotify_id is already tracked, do nothing (a save/import for it already exists)."""
        with self._sf() as session:
            stmt = pg_insert(Album).values(
                spotify_id=spotify_id,
                artist=artist,
                title=title,
                mb_releasegroup_id=mb_releasegroup_id,
                art_url=art_url,
                state=AlbumState.owned,
                provenance=Provenance.manual,
                owned_beets_id=beets_id,
                owned_link_source=LinkSource.manual,
            )
            if spotify_id is not None:
                stmt = stmt.on_conflict_do_nothing(index_elements=["spotify_id"])
            session.execute(stmt)
            session.commit()

    # --- releases / artist-watch (§6b) -----------------------------------------------

    def suggested_queue(self) -> list[SuggestedRow]:
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.id, Album.artist, Album.title, has_art)
                .where(Album.state == AlbumState.suggested)
                .order_by(Album.artist, Album.title)
            )
            return [SuggestedRow(r[0], r[1], r[2], r[3]) for r in rows]

    def seen_album_ids(self) -> set[str]:
        with self._sf() as session:
            return set(session.scalars(select(SeenRelease.spotify_album_id)))

    def artist_has_baseline(self, artist_id: str) -> bool:
        with self._sf() as session:
            return (
                session.scalar(
                    select(SeenRelease.spotify_album_id).where(SeenRelease.artist_id == artist_id)
                )
                is not None
            )

    def mark_seen(self, pairs: list[tuple[str, str]]) -> None:
        """Record (album id, artist id) as accounted-for by the watch; ignore duplicates."""
        if not pairs:
            return
        with self._sf() as session:
            session.execute(
                pg_insert(SeenRelease)
                .values([{"spotify_album_id": a, "artist_id": art} for a, art in pairs])
                .on_conflict_do_nothing(index_elements=["spotify_album_id"])
            )
            session.commit()

    def spotify_id_of(self, album_id: int) -> str | None:
        with self._sf() as session:
            return session.execute(
                select(Album.spotify_id).where(Album.id == album_id)
            ).scalar_one_or_none()

    def transition_suggested(
        self,
        album_id: int,
        state: AlbumState,
        *,
        saved_at: datetime | None,
        verdict_at: datetime | None,
    ) -> None:
        """Move a `suggested` album onward (Save/Want/Dismiss, §6b)."""
        values: dict[str, object] = {"state": state}
        if saved_at is not None:
            values["saved_at"] = saved_at
        if verdict_at is not None:
            values["verdict_at"] = verdict_at
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.suggested)
                .values(**values)
            )
            session.commit()

    # --- import auto-land, both fronts (§12 Transmission / §13 watch-dir) -------------

    def known_source_keys(self) -> set[str]:
        """Per-source keys already recorded — the seen ledger so an acquisition (torrent
        completion / watch-dir drop) is only ever processed once."""
        with self._sf() as session:
            return set(session.scalars(select(PendingImport.source_key)))

    def wanted_for_matching(self) -> list[WantedForMatch]:
        """`wanted` albums an acquisition could be fulfilling (§12/§13 match)."""
        targets = (AlbumState.wanted,)
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.artist, Album.title).where(Album.state.in_(targets))
            )
            return [WantedForMatch(*row) for row in rows]

    def add_pending_import(
        self,
        *,
        source: ImportSource,
        source_key: str,
        name: str,
        download_dir: str | None = None,
        files: list[str] | None = None,
        archive_path: str | None = None,
        matched_album_id: int | None,
    ) -> None:
        with self._sf() as session:
            session.execute(
                pg_insert(PendingImport)
                .values(
                    source=source,
                    source_key=source_key,
                    name=name,
                    download_dir=download_dir,
                    files=files or [],
                    archive_path=archive_path,
                    matched_album_id=matched_album_id,
                )
                .on_conflict_do_nothing(index_elements=["source_key"])
            )
            session.commit()

    def list_imports(self) -> list[ImportRow]:
        """All recent acquisitions with their status, so the Import screen shows a task list
        that persists (detected → queued → imported/failed) rather than rows vanishing on
        click. Active ones (detected/queued) first, then the rest, each by download name."""
        active = (ImportState.detected, ImportState.queued)
        with self._sf() as session:
            rows = session.execute(
                select(
                    PendingImport.id,
                    PendingImport.source,
                    PendingImport.name,
                    PendingImport.state,
                    PendingImport.matched_album_id,
                    Album.artist,
                    Album.title,
                )
                .outerjoin(Album, Album.id == PendingImport.matched_album_id)
                .order_by(
                    PendingImport.state.in_(active).desc(),  # active first
                    func.lower(PendingImport.name),
                )
            )
            return [ImportRow(r[0], r[1].value, r[2], r[3].value, r[4], r[5], r[6]) for r in rows]

    def count_active_imports(self) -> int:
        """Imports awaiting a click or still processing — the dashboard's Import count."""
        active = (ImportState.detected, ImportState.queued)
        with self._sf() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(PendingImport)
                    .where(PendingImport.state.in_(active))
                )
                or 0
            )

    def queue_import(self, import_id: int) -> None:
        """Mark an import for background processing. Allowed from detected (the Import click)
        or failed (a retry); ignored otherwise so a double-click can't re-run a done import."""
        with self._sf() as session:
            session.execute(
                update(PendingImport)
                .where(
                    PendingImport.id == import_id,
                    PendingImport.state.in_((ImportState.detected, ImportState.failed)),
                )
                .values(state=ImportState.queued)
            )
            session.commit()

    def queued_import_ids(self) -> list[int]:
        with self._sf() as session:
            return list(
                session.scalars(
                    select(PendingImport.id).where(PendingImport.state == ImportState.queued)
                )
            )

    def get_pending_import(self, import_id: int) -> ImportRecord | None:
        with self._sf() as session:
            row = session.get(PendingImport, import_id)
            if row is None:
                return None
            return ImportRecord(
                id=row.id,
                source=row.source.value,
                download_dir=row.download_dir,
                files=list(row.files),
                archive_path=row.archive_path,
                matched_album_id=row.matched_album_id,
                state=row.state.value,
            )

    def mark_import(self, import_id: int, state: ImportState) -> None:
        with self._sf() as session:
            session.execute(
                update(PendingImport).where(PendingImport.id == import_id).values(state=state)
            )
            session.commit()

    # --- notification dedup flags (§8d) ----------------------------------------------

    def notification_flags(self) -> tuple[bool, bool]:
        with self._sf() as session:
            row = session.get(NotificationState, 1)
            return (row.reauth_notified, row.triage_notified) if row else (False, False)

    def set_notification_flags(
        self, *, reauth_notified: bool | None = None, triage_notified: bool | None = None
    ) -> None:
        with self._sf() as session:
            row = session.get(NotificationState, 1)
            if row is None:
                row = NotificationState(id=1)
                session.add(row)
            if reauth_notified is not None:
                row.reauth_notified = reauth_notified
            if triage_notified is not None:
                row.triage_notified = triage_notified
            session.commit()

    def count_by_state(self) -> dict[str, int]:
        with self._sf() as session:
            rows = session.execute(select(Album.state, func.count()).group_by(Album.state))
            return {state.value: count for state, count in rows}

    def count_missing_art(self) -> int:
        """Albums with a source art URL but no stored blob — a §16 backlog gauge."""
        with self._sf() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(Album)
                    .outerjoin(AlbumArt, AlbumArt.album_id == Album.id)
                    .where(Album.art_url.is_not(None), AlbumArt.album_id.is_(None))
                )
                or 0
            )

    # --- job heartbeats / metrics (§16) ----------------------------------------------

    def record_job_success(self, job: str, at: datetime) -> None:
        self._upsert_job(job, last_run_at=at, last_success_at=at, runs_delta=1)

    def record_job_error(self, job: str, at: datetime) -> None:
        self._upsert_job(job, last_run_at=at, last_error_at=at, errors_delta=1)

    def _upsert_job(
        self,
        job: str,
        *,
        last_run_at: datetime,
        last_success_at: datetime | None = None,
        last_error_at: datetime | None = None,
        runs_delta: int = 0,
        errors_delta: int = 0,
    ) -> None:
        with self._sf() as session:
            values: dict[str, object] = {
                "job": job,
                "last_run_at": last_run_at,
                "last_success_at": last_success_at,
                "last_error_at": last_error_at,
                "runs": runs_delta,
                "errors": errors_delta,
            }
            update: dict[str, object] = {"last_run_at": last_run_at}
            if last_success_at is not None:
                update["last_success_at"] = last_success_at
            if last_error_at is not None:
                update["last_error_at"] = last_error_at
            if runs_delta:
                update["runs"] = JobRun.runs + runs_delta
            if errors_delta:
                update["errors"] = JobRun.errors + errors_delta
            stmt = pg_insert(JobRun).values(**values)
            session.execute(stmt.on_conflict_do_update(index_elements=["job"], set_=update))
            session.commit()

    def job_runs(self) -> list[JobRunRow]:
        with self._sf() as session:
            rows = session.execute(
                select(JobRun.job, JobRun.last_success_at, JobRun.runs, JobRun.errors).order_by(
                    JobRun.job
                )
            )
            return [JobRunRow(*row) for row in rows]

    # --- library view ----------------------------------------------------------------

    def list_albums(self, state: str | None = None) -> list[AlbumSummary]:
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            stmt = select(
                Album.id,
                Album.artist,
                Album.title,
                Album.state,
                Album.mb_releasegroup_id,
                has_art,
            ).order_by(Album.artist, Album.title)
            if state is not None:
                stmt = stmt.where(Album.state == AlbumState(state))
            return [
                AlbumSummary(
                    id=row[0],
                    artist=row[1],
                    title=row[2],
                    state=row[3].value,
                    mb_releasegroup_id=row[4],
                    owned=row[3] == AlbumState.owned,
                    has_art=row[5],
                )
                for row in session.execute(stmt)
            ]
