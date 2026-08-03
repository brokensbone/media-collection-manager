from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from ..domain.verdict import PlayStat
from ..models import (
    Album,
    AlbumArt,
    AlbumState,
    ImportSource,
    ImportState,
    ImportTarget,
    JobRun,
    LinkSource,
    MediaKind,
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
    spotify_id: str | None


@dataclass
class OwnedEnrichment:
    """What the DB adds to a beets-owned album matched on release-group id: the tracked album's
    id (so its stored cover art can be shown) and its Spotify id (present iff it's in your saves,
    so the Owned view can both flag it and link the cover to the album on Spotify)."""

    album_id: int
    has_art: bool
    spotify_id: str | None


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
    spotify_id: str | None


@dataclass
class SuggestedRow:
    id: int
    artist: str
    title: str
    has_art: bool
    spotify_id: str | None


@dataclass
class MatchCandidate:
    id: int
    artist: str
    title: str


@dataclass
class ImportRow:
    id: int
    source: str
    name: str
    media_kind: str
    import_target: str
    classification_detail: str | None
    destination_path: str | None
    state: str
    matched_album_id: int | None
    matched_artist: str | None
    matched_title: str | None
    matched_state: str | None  # the matched album's state, so the UI can flag "already owned"
    archive_path: str | None
    error_detail: str | None  # why the last import attempt failed (failed rows only)
    updated_at: str | None  # ISO time of the last state change; drives Tasks order + window
    created_at: str | None  # ISO time the drop was first detected; the Import list's discovery day


@dataclass
class TransmissionRow:
    id: int
    name: str
    media_kind: str
    import_target: str
    classification_detail: str | None
    destination_path: str | None
    state: str
    matched: str | None  # "Artist — Title" of the matched album, if any
    has_audio: bool | None  # False = skipped as non-music; None = not screened


@dataclass
class ImportRecord:
    id: int
    source: str
    name: str
    media_kind: str
    import_target: str
    download_dir: str | None
    files: list[str]
    archive_path: str | None
    destination_path: str | None
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

    def owned_without_art(self) -> list[MatchCandidate]:
        """Owned albums with no cover at all — no source URL and no stored blob. Candidates for a
        Spotify art lookup (e.g. imported via Transmission/beets with no Spotify match, or while
        Spotify was disconnected)."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.artist, Album.title)
                .outerjoin(AlbumArt, AlbumArt.album_id == Album.id)
                .where(
                    Album.state == AlbumState.owned,
                    Album.art_url.is_(None),
                    AlbumArt.album_id.is_(None),
                )
            )
            return [MatchCandidate(*row) for row in rows]

    def set_art_url(self, album_id: int, art_url: str) -> None:
        with self._sf() as session:
            session.execute(update(Album).where(Album.id == album_id).values(art_url=art_url))
            session.commit()

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

    def albums_needing_resolution(
        self, *, backoff_base_seconds: int, backoff_cap_seconds: int
    ) -> list[UnresolvedAlbum]:
        """Non-dismissed albums without a release-group id that are *due* a resolution attempt.
        Least-tried first (then oldest): a capped pass always reaches fresh albums before
        re-grinding the MB-absent tail, so repeated no-matches can't starve the queue (§5).

        Due = never attempted, or the exponential backoff window since the last "no match" has
        elapsed: min(cap, base * 2**attempts) seconds. So a release MB doesn't have decays from
        hourly retries to at most ~weekly instead of being re-queried every reconcile (§11)."""
        # power(2, attempts) with a big attempts count would overflow; the exponent is clamped
        # (the cap dominates long before it matters — base * 2**20 already far exceeds a week).
        window = func.least(
            backoff_cap_seconds,
            backoff_base_seconds * func.power(2, func.least(Album.resolution_attempts, 20)),
        )
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.spotify_id, Album.upc, Album.artist, Album.title)
                .where(
                    Album.mb_releasegroup_id.is_(None),
                    Album.state != AlbumState.dismissed,
                    or_(
                        Album.last_resolution_attempt.is_(None),
                        func.extract("epoch", func.now() - Album.last_resolution_attempt) >= window,
                    ),
                )
                .order_by(Album.resolution_attempts.asc(), Album.id.asc())
            )
            return [UnresolvedAlbum(*row) for row in rows]

    def bump_resolution_attempts(self, album_ids: list[int]) -> None:
        """Record a failed resolution attempt (a genuine "no match", not an upstream error), so
        the album sinks in the least-tried order and its backoff window grows. Stamps the attempt
        time so albums_needing_resolution can hold it back until the window elapses."""
        if not album_ids:
            return
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id.in_(album_ids))
                .values(
                    resolution_attempts=Album.resolution_attempts + 1,
                    last_resolution_attempt=func.now(),
                )
            )
            session.commit()

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

    def labels_for(self, album_ids: list[int]) -> dict[int, str]:
        """`Artist — Title` per album id, for activity-feed messages."""
        if not album_ids:
            return {}
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.artist, Album.title).where(Album.id.in_(album_ids))
            )
            return {aid: f"{artist} — {title}" for aid, artist, title in rows}

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
                select(Album.id, Album.artist, Album.title, has_art, Album.spotify_id)
                .where(Album.state == AlbumState.wanted)
                .order_by(Album.artist, Album.title)
            )
            return [AcquireRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]

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
    ) -> int | None:
        """Record a directly-imported album as owned (D21 reverse-match), so it shows in Owned.
        Sticky manual link (reconcile never clobbers it); art back-fills via the art job. If the
        spotify_id is already tracked, do nothing (a save/import for it already exists). Returns
        the album id (created, or the existing one on conflict) so the import row can link to it."""
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
            new_id = session.scalar(stmt.returning(Album.id))
            session.commit()
            if new_id is not None:
                return int(new_id)
            if spotify_id is not None:  # conflicted with an existing row
                return session.scalar(select(Album.id).where(Album.spotify_id == spotify_id))
            return None

    # --- releases / artist-watch (§6b) -----------------------------------------------

    def suggested_queue(self) -> list[SuggestedRow]:
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.id, Album.artist, Album.title, has_art, Album.spotify_id)
                .where(Album.state == AlbumState.suggested)
                .order_by(Album.artist, Album.title)
            )
            return [SuggestedRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]

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

    def albums_for_matching(self) -> list[MatchCandidate]:
        """Every album an acquisition could correspond to (§12/§13 match) — the whole funnel,
        not just `wanted`. A drop for something in Decide (`saved`) or freshly `suggested` is a
        valid match, and so is one for an album you *already own* (a re-download worth flagging,
        and matching it skips the reverse-match that would otherwise mint a duplicate owned
        entry). Ownership is still decided by reconcile via release-group; this only labels."""
        with self._sf() as session:
            rows = session.execute(select(Album.id, Album.artist, Album.title))
            return [MatchCandidate(*row) for row in rows]

    def add_pending_import(
        self,
        *,
        source: ImportSource,
        source_key: str,
        name: str,
        media_kind: MediaKind = MediaKind.music,
        import_target: ImportTarget = ImportTarget.beets,
        classification_detail: str | None = None,
        destination_path: str | None = None,
        download_dir: str | None = None,
        files: list[str] | None = None,
        archive_path: str | None = None,
        matched_album_id: int | None,
        state: ImportState = ImportState.detected,
        has_audio: bool | None = None,
    ) -> None:
        with self._sf() as session:
            session.execute(
                pg_insert(PendingImport)
                .values(
                    source=source,
                    source_key=source_key,
                    name=name,
                    media_kind=media_kind,
                    import_target=import_target,
                    classification_detail=classification_detail,
                    destination_path=destination_path,
                    download_dir=download_dir,
                    files=files or [],
                    archive_path=archive_path,
                    matched_album_id=matched_album_id,
                    state=state,
                    has_audio=has_audio,
                )
                .on_conflict_do_nothing(index_elements=["source_key"])
            )
            session.commit()

    # Columns for an ImportRow, in the order _import_rows() unpacks them.
    _IMPORT_COLS = (  # noqa: RUF012 (a fixed column spec, not mutable shared state)
        PendingImport.id,
        PendingImport.source,
        PendingImport.name,
        PendingImport.media_kind,
        PendingImport.import_target,
        PendingImport.classification_detail,
        PendingImport.destination_path,
        PendingImport.state,
        PendingImport.matched_album_id,
        Album.artist,
        Album.title,
        Album.state,
        PendingImport.archive_path,
        PendingImport.error_detail,
        PendingImport.updated_at,
        PendingImport.created_at,
    )

    def _import_rows(self, *conditions: Any, order_by: Any) -> list[ImportRow]:
        with self._sf() as session:
            rows = session.execute(
                select(*self._IMPORT_COLS)
                .outerjoin(Album, Album.id == PendingImport.matched_album_id)
                .where(*conditions)
                .order_by(*order_by)
            )
            return [
                ImportRow(
                    id=r[0],
                    source=r[1].value,
                    name=r[2],
                    media_kind=r[3].value,
                    import_target=r[4].value,
                    classification_detail=r[5],
                    destination_path=r[6],
                    state=r[7].value,
                    matched_album_id=r[8],
                    matched_artist=r[9],
                    matched_title=r[10],
                    matched_state=r[11].value if r[11] is not None else None,
                    archive_path=r[12],
                    error_detail=r[13],
                    updated_at=r[14].isoformat() if r[14] is not None else None,
                    created_at=r[15].isoformat() if r[15] is not None else None,
                )
                for r in rows
            ]

    def pending_imports(self) -> list[ImportRow]:
        """The Import worklist: downloads still awaiting a decision (detected), including the
        review tail. Once Import is clicked they leave here and become a Task."""
        return self._import_rows(
            PendingImport.state == ImportState.detected,
            # Newest discovery first so freshly-added drops surface at the top; the UI groups by
            # discovery day. Name is only a stable tiebreak within a day.
            order_by=(
                PendingImport.created_at.desc().nullslast(),
                func.lower(PendingImport.name),
            ),
        )

    def task_imports(self, completed_since: datetime) -> list[ImportRow]:
        """The Tasks view: everything acted on — in progress, queued, failed — plus completed
        (imported/skipped) within the recent window. Newest activity first."""
        terminal_recent = and_(
            PendingImport.state.in_((ImportState.imported, ImportState.skipped)),
            PendingImport.updated_at >= completed_since,
        )
        return self._import_rows(
            or_(
                PendingImport.state.in_(
                    (ImportState.importing, ImportState.queued, ImportState.failed)
                ),
                terminal_recent,
            ),
            order_by=(PendingImport.updated_at.desc().nullslast(), PendingImport.id.desc()),
        )

    def completed_imports(self) -> list[ImportRow]:
        """The archive: every completed import (imported/skipped), whatever its age. Newest
        first. Reached from the Tasks view when the recent window isn't enough."""
        return self._import_rows(
            PendingImport.state.in_((ImportState.imported, ImportState.skipped)),
            order_by=(PendingImport.updated_at.desc().nullslast(), PendingImport.id.desc()),
        )

    def list_imports(self) -> list[ImportRow]:
        """Every non-dismissed acquisition with its status, active first. Broad query used by
        detection tests; the UI uses the narrower pending/task/completed views."""
        active = (ImportState.detected, ImportState.queued, ImportState.importing)
        return self._import_rows(
            PendingImport.state != ImportState.dismissed,
            order_by=(PendingImport.state.in_(active).desc(), func.lower(PendingImport.name)),
        )

    def transmission_ledger(self) -> list[TransmissionRow]:
        """Every Transmission torrent the app has seen, whatever its state — including ones
        skipped as non-music (dismissed with has_audio=False). Powers the Transmission page's
        full list; newest first."""
        with self._sf() as session:
            rows = session.execute(
                select(
                    PendingImport.id,
                    PendingImport.name,
                    PendingImport.media_kind,
                    PendingImport.import_target,
                    PendingImport.classification_detail,
                    PendingImport.destination_path,
                    PendingImport.state,
                    Album.artist,
                    Album.title,
                    PendingImport.has_audio,
                )
                .outerjoin(Album, Album.id == PendingImport.matched_album_id)
                .where(PendingImport.source == ImportSource.transmission)
                .order_by(PendingImport.created_at.desc(), func.lower(PendingImport.name))
            )
            return [
                TransmissionRow(
                    id=r[0],
                    name=r[1],
                    media_kind=r[2].value,
                    import_target=r[3].value,
                    classification_detail=r[4],
                    destination_path=r[5],
                    state=r[6].value,
                    matched=f"{r[7]} — {r[8]}" if r[7] is not None else None,
                    has_audio=r[9],
                )
                for r in rows
            ]

    def _count_imports(self, states: tuple[ImportState, ...]) -> int:
        with self._sf() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(PendingImport)
                    .where(PendingImport.state.in_(states))
                )
                or 0
            )

    def count_pending_imports(self) -> int:
        """Downloads awaiting an Import/Discard decision — the dashboard's Import count."""
        return self._count_imports((ImportState.detected,))

    def count_task_imports(self) -> int:
        """In-flight and needs-attention imports (queued, importing, failed) — the Tasks count."""
        return self._count_imports((ImportState.queued, ImportState.importing, ImportState.failed))

    def count_active_imports(self) -> int:
        """Detected + queued + importing — an import that isn't done yet, either way."""
        return self._count_imports(
            (ImportState.detected, ImportState.queued, ImportState.importing)
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
                .values(state=ImportState.queued, updated_at=func.now())
            )
            session.commit()

    def queued_import_ids(self) -> list[int]:
        with self._sf() as session:
            return list(
                session.scalars(
                    select(PendingImport.id).where(PendingImport.state == ImportState.queued)
                )
            )

    def requeue_importing(self) -> None:
        """Reset any import stuck at `importing` back to `queued` — it was interrupted by a
        worker restart mid-import, so it should retry rather than be stranded."""
        with self._sf() as session:
            session.execute(
                update(PendingImport)
                .where(PendingImport.state == ImportState.importing)
                .values(state=ImportState.queued, updated_at=func.now())
            )
            session.commit()

    def get_pending_import(self, import_id: int) -> ImportRecord | None:
        with self._sf() as session:
            row = session.get(PendingImport, import_id)
            if row is None:
                return None
            return ImportRecord(
                id=row.id,
                source=row.source.value,
                name=row.name,
                media_kind=row.media_kind.value,
                import_target=row.import_target.value,
                download_dir=row.download_dir,
                files=list(row.files),
                archive_path=row.archive_path,
                destination_path=row.destination_path,
                matched_album_id=row.matched_album_id,
                state=row.state.value,
            )

    def mark_import(self, import_id: int, state: ImportState) -> None:
        # Any non-failed transition clears a stale error from a previous attempt (e.g. a retry
        # that's now importing, or that succeeded/skipped) so the UI never shows an old failure.
        with self._sf() as session:
            session.execute(
                update(PendingImport)
                .where(PendingImport.id == import_id)
                .values(state=state, error_detail=None, updated_at=func.now())
            )
            session.commit()

    def mark_import_failed(self, import_id: int, error_detail: str) -> None:
        """Mark an import failed and record why, so a failed row can show its log (§12)."""
        with self._sf() as session:
            session.execute(
                update(PendingImport)
                .where(PendingImport.id == import_id)
                .values(state=ImportState.failed, error_detail=error_detail, updated_at=func.now())
            )
            session.commit()

    def set_import_match(self, import_id: int, album_id: int) -> None:
        """Point an import row at the album it produced — used after a reverse-match creates an
        owned album, so the row shows that album instead of a stale 'no match'."""
        with self._sf() as session:
            session.execute(
                update(PendingImport)
                .where(PendingImport.id == import_id)
                .values(matched_album_id=album_id)
            )
            session.commit()

    def dismiss_import(self, import_id: int) -> None:
        """Discard an import the operator doesn't want (non-music that slipped through, a
        re-download of something already owned). Sticky: the row is kept as `dismissed` so its
        source_key stays in the seen-ledger and a still-seeding torrent isn't re-detected next
        poll. Hidden from the Import list."""
        with self._sf() as session:
            session.execute(
                update(PendingImport)
                .where(PendingImport.id == import_id)
                .values(state=ImportState.dismissed)
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

    def resolution_counts(self) -> tuple[int, int]:
        """(resolved, unresolved) — albums with a MusicBrainz release-group vs the non-dismissed
        ones still awaiting one. Drives the cold-start resolution-progress indicator."""
        with self._sf() as session:
            resolved = session.scalar(
                select(func.count()).select_from(Album).where(Album.mb_releasegroup_id.is_not(None))
            )
            unresolved = session.scalar(
                select(func.count())
                .select_from(Album)
                .where(Album.mb_releasegroup_id.is_(None), Album.state != AlbumState.dismissed)
            )
            return int(resolved or 0), int(unresolved or 0)

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

    def enrichment_by_release_group(self) -> dict[str, OwnedEnrichment]:
        """Per release-group id, the tracked album to enrich a beets-owned row with (cover art +
        Spotify presence). Keyed by rgid; if several albums share one, the row that has art wins
        (so the Owned view shows a cover when any edition has one)."""
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.mb_releasegroup_id, Album.id, has_art, Album.spotify_id)
                .where(Album.mb_releasegroup_id.is_not(None))
                .order_by(has_art.desc(), Album.id)
            )
            out: dict[str, OwnedEnrichment] = {}
            for rgid, album_id, art, spotify_id in rows:
                if rgid not in out:
                    out[rgid] = OwnedEnrichment(
                        album_id=album_id, has_art=bool(art), spotify_id=spotify_id
                    )
            return out

    def enrichment_by_beets_id(self) -> dict[str, OwnedEnrichment]:
        """Per beets id, the album row explicitly linked to it via `owned_beets_id` (D21
        reverse-match / manual link). The rgid join can't reach as-is albums that have no
        release-group id, but their reverse-match rows carry the beets id — so this is the Owned
        view's fallback enrichment for them (cover art + Spotify out-link)."""
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.owned_beets_id, Album.id, has_art, Album.spotify_id)
                .where(Album.owned_beets_id.is_not(None))
                .order_by(has_art.desc(), Album.id)
            )
            out: dict[str, OwnedEnrichment] = {}
            for beets_id, album_id, art, spotify_id in rows:
                if beets_id not in out:
                    out[beets_id] = OwnedEnrichment(
                        album_id=album_id, has_art=bool(art), spotify_id=spotify_id
                    )
            return out

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
                Album.spotify_id,
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
                    spotify_id=row[6],
                )
                for row in session.execute(stmt)
            ]
