import errno
import logging
import os
import re
import shutil
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, overload

from .adapters.album_repo import AlbumRepo, ImportRecord, ImportRow
from .adapters.beets import BeetsAlbum
from .adapters.event_log import NullEventSink
from .adapters.unpack import dispose, unpack
from .domain.match import MatchTarget, best_match
from .models import AlbumState, ImportSource, ImportState, ImportTarget, MediaKind
from .ports.clock import Clock
from .ports.events import EventSink
from .ports.file_transfer import FileTransfer
from .ports.tags import TagReader
from .ports.transmission import TransmissionClient
from .reverse_match import ReverseMatcher

log = logging.getLogger(__name__)


class BeetsImporter(Protocol):
    """The beets import seam we depend on (a subset of BeetsClient, SPEC §5/§12)."""

    def import_dir(self, path: str) -> None: ...


class LibraryCatalog(Protocol):
    """The beets catalogue seam — used to diff the library before/after an import so a
    directly-imported album can be identified for reverse-match (D21)."""

    def all_albums(self) -> list[BeetsAlbum]: ...


@dataclass
class DetectResult:
    detected: int


@dataclass
class ImportItem:
    id: int
    source: str
    name: str
    media_kind: str
    import_target: str
    classification_detail: str | None
    destination_path: str | None
    state: str  # detected | queued | imported | failed — drives the status shown per row
    matched_album_id: int | None
    matched: str | None  # "Artist — Title" of the matched want, or None for the no-match tail
    matched_owned: bool  # the matched album is already owned — importing would just duplicate it
    missing: bool  # the watch-dir file backing this drop is gone — offer removal, not import
    error_detail: str | None  # why the last attempt failed (failed rows only), for the log view
    updated_at: str | None  # ISO time of the last state change (Tasks/Archive show "when")
    created_at: str | None  # ISO time first detected — the Import list groups by discovery day


@dataclass
class Classification:
    media_kind: MediaKind
    import_target: ImportTarget
    classification_detail: str
    destination_path: str | None
    state: ImportState
    matched_album_id: int | None = None


# --- detection: one service per front (§12 Transmission / §13 watch-dir) --------------


class ImportDetectionService:
    """Polls Transmission for completed downloads, records each once (hash ledger), and
    fuzzy-matches it to a wanted album (SPEC §12). Unmatched downloads are still recorded
    so the operator can hand-import them (the no-match tail)."""

    def __init__(
        self,
        *,
        transmission: TransmissionClient,
        repo: AlbumRepo,
        match_threshold: float,
        tv_root: str = "",
        film_root: str = "",
        workspace_root: str = "",
        events: EventSink | None = None,
    ):
        self._transmission = transmission
        self._repo = repo
        self._threshold = match_threshold
        self._tv_root = tv_root
        self._film_root = film_root
        self._workspace_root = workspace_root
        self._events = events or NullEventSink()

    def poll(self) -> DetectResult:
        # The client is shared with all the operator's torrents, so on first connect there are
        # hundreds already complete and plenty are not importable media. Each hash is screened
        # once and recorded in the ledger so re-polls skip it entirely.
        known = self._repo.known_source_keys()
        fresh = [t for t in self._transmission.completed_torrents() if t.hash not in known]
        if not fresh:
            return DetectResult(detected=0)

        targets = _match_targets(self._repo)
        detected = 0
        for t in fresh:
            classified = _classify_torrent(
                t.name,
                t.files,
                tv_root=self._tv_root,
                film_root=self._film_root,
                workspace_root=self._workspace_root,
                matched_album_id=best_match(t.name, targets, self._threshold),
            )
            self._repo.add_pending_import(
                source=ImportSource.transmission,
                source_key=t.hash,
                name=t.name,
                media_kind=classified.media_kind,
                import_target=classified.import_target,
                classification_detail=classified.classification_detail,
                destination_path=classified.destination_path,
                download_dir=t.download_dir,
                files=t.files,
                matched_album_id=classified.matched_album_id,
                state=classified.state,
                has_audio=classified.media_kind == MediaKind.music,
            )
            if classified.state != ImportState.dismissed:
                detected += 1
                self._events.emit(
                    job="import", type="detected", message=f"Detected download: '{t.name}'"
                )
        return DetectResult(detected=detected)


class WatchdirDetectionService:
    """Scans a watch directory for settled Bandcamp zips / dropped folders, records each once
    (path+size+mtime ledger), and matches it to a wanted album using its embedded audio tags
    (a stronger signal than the filename, SPEC §13), falling back to the name."""

    def __init__(
        self,
        *,
        repo: AlbumRepo,
        tags: TagReader,
        clock: Clock,
        watch_dir: str,
        archive_subdir: str,
        settle_seconds: int,
        match_threshold: float,
        events: EventSink | None = None,
    ):
        self._repo = repo
        self._tags = tags
        self._clock = clock
        self._watch_dir = watch_dir
        self._archive_subdir = archive_subdir
        self._settle_seconds = settle_seconds
        self._threshold = match_threshold
        self._events = events or NullEventSink()

    def poll(self, *, force: bool = False) -> DetectResult:
        root = Path(self._watch_dir)
        if not root.is_dir():
            return DetectResult(detected=0)

        known = self._repo.known_source_keys()
        cutoff = self._clock.now() - timedelta(seconds=self._settle_seconds)
        fresh = [
            drop
            for drop in self._settled_drops(root, cutoff, force=force)
            if _drop_key(drop) not in known
        ]
        if not fresh:
            return DetectResult(detected=0)

        targets = _match_targets(self._repo)
        for drop in fresh:
            tags = self._tags.read(drop)
            query = f"{tags[0]} {tags[1]}" if tags else drop.stem
            self._repo.add_pending_import(
                source=ImportSource.watchdir,
                source_key=_drop_key(drop),
                name=drop.name,
                media_kind=MediaKind.music,
                import_target=ImportTarget.beets,
                classification_detail="Watch-folder audio drop.",
                archive_path=str(drop),
                matched_album_id=best_match(query, targets, self._threshold),
            )
            self._events.emit(
                job="watchdir", type="detected", message=f"Detected drop: '{drop.name}'"
            )
        return DetectResult(detected=len(fresh))

    def _settled_drops(self, root: Path, cutoff: datetime, *, force: bool = False) -> list[Path]:
        drops = []
        for entry in sorted(root.iterdir()):
            if entry.name == self._archive_subdir:
                continue  # never re-ingest what we archived
            if entry.is_file() and entry.suffix.lower() != ".zip":
                continue
            if entry.is_dir() and not _dir_has_audio(entry):
                continue
            if force or _newest_mtime(entry) <= cutoff:  # settle check: not still being written
                drops.append(entry)
        return drops


# --- the shared import tail (§12/§13): stage → beets import → tidy → dispose -----------


class Stager(Protocol):
    """Stages a detected acquisition into a local folder for beets, and finalizes its source
    after a successful import. The only per-front difference in the import tail (SPEC §12/§13)."""

    def stage(self, rec: ImportRecord, dest: str) -> None: ...
    def finalize(self, rec: ImportRecord) -> None: ...


class TransmissionStager:
    """§12: rsync the torrent's files off the seedbox; never touch the source (seeding-safe)."""

    def __init__(self, transfer: FileTransfer):
        self._transfer = transfer

    def stage(self, rec: ImportRecord, dest: str) -> None:
        assert rec.download_dir is not None  # always set for transmission rows
        self._transfer.fetch(download_dir=rec.download_dir, files=rec.files, dest=dest)

    def finalize(self, rec: ImportRecord) -> None:
        pass  # the seedbox originals are never moved or deleted


class WatchdirStager:
    """§13: unpack the local zip/folder; the drop is ours, so dispose of it post-import."""

    def __init__(self, *, watch_dir: str, disposition: str, archive_subdir: str):
        self._archive_dir = str(Path(watch_dir) / archive_subdir)
        self._disposition = disposition

    def stage(self, rec: ImportRecord, dest: str) -> None:
        assert rec.archive_path is not None  # always set for watch-dir rows
        unpack(rec.archive_path, dest)

    def finalize(self, rec: ImportRecord) -> None:
        assert rec.archive_path is not None
        dispose(rec.archive_path, disposition=self._disposition, archive_dir=self._archive_dir)


class VideoLibraryImporter:
    """Places staged video files into their canonical library destination. Returns the number of
    files actually moved; files already present at the destination are skipped, not overwritten,
    so re-importing a pack that's already (partly) in the library is a no-op for those files —
    mirroring how the beets path treats a duplicate (D21)."""

    def import_dir(self, staged: str, destination: str) -> int:
        source_root = _content_root(Path(staged))
        target_root = Path(destination)
        target_root.mkdir(parents=True, exist_ok=True)
        return sum(_move_into(child, target_root / child.name) for child in source_root.iterdir())


class ImportRunner:
    """The shared import tail (SPEC §12/§13): stage the acquisition into the beets inbox via
    the source's stager, import it, tidy the staging, then let the stager dispose the source.
    Ownership flips to `owned` on the next reconcile via the release-group match."""

    def __init__(
        self,
        *,
        repo: AlbumRepo,
        stagers: dict[ImportSource, Stager],
        beets: BeetsImporter,
        video: VideoLibraryImporter,
        inbox: str,
        catalog: LibraryCatalog | None = None,
        reverse_matcher: ReverseMatcher | None = None,
        events: EventSink | None = None,
    ):
        self._repo = repo
        self._stagers = stagers
        self._beets = beets
        self._video = video
        self._inbox = inbox
        self._catalog = catalog
        self._reverse_matcher = reverse_matcher
        self._events = events or NullEventSink()

    def run(self, import_id: int) -> None:
        rec = self._repo.get_pending_import(import_id)
        if rec is None or rec.state != ImportState.queued.value:
            return  # only queued imports are processed (the click/retry enqueues them)
        stager = self._stagers[ImportSource(rec.source)]
        self._repo.mark_import(import_id, ImportState.importing)  # so the UI shows the active one
        self._events.emit(
            job="import",
            type="importing",
            message=f"Importing '{rec.name}'…",
            album_id=rec.matched_album_id,
        )

        before = self._album_ids()  # snapshot to identify what this import adds (D21)
        new: list[BeetsAlbum] = []
        placed_video = 0
        staging = Path(self._inbox) / str(rec.id)  # unique per import; no name-collisions
        try:
            stager.stage(rec, str(staging))
            if rec.import_target == ImportTarget.beets.value:
                self._beets.import_dir(str(staging))
                new = self._new_albums(before)
            elif rec.import_target in (
                ImportTarget.tv.value,
                ImportTarget.film.value,
                ImportTarget.workspace.value,
            ):
                if not rec.destination_path:
                    raise RuntimeError("video import missing destination path")
                placed_video = self._video.import_dir(str(staging), rec.destination_path)
            else:
                raise RuntimeError("import target is review-only")
        except Exception as exc:
            detail = _error_detail(exc)
            self._repo.mark_import_failed(import_id, detail)
            # Log it (with the traceback) AND persist it on the row: a failed import must never
            # die silently — the operator can read `detail` from the Import screen, and it's in
            # the worker log too. Logged here (once, richly) rather than in run_queued's catch.
            log.warning("import %s (%s) failed: %s", import_id, rec.name, exc, exc_info=True)
            self._events.emit(
                job="import",
                type="failed",
                message=f"Import failed: '{rec.name}'",
                album_id=rec.matched_album_id,
            )
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)  # tidy the local staging either way

        # A no-op import — already wholly in the library — is neither a failure nor a second copy:
        # record it skipped and leave the source in place (we only ever dispose what we actually
        # imported). beets signals this by adding nothing (duplicate_action: skip); a video import
        # signals it by moving nothing (every file already present at the destination). "nothing
        # new" is meaningless for a video, so this must be gated per target — not on `new` alone,
        # which is always empty for the video path.
        if rec.import_target == ImportTarget.beets.value:
            is_noop = self._catalog is not None and not new
        else:
            is_noop = placed_video == 0
        if is_noop:
            self._repo.mark_import(import_id, ImportState.skipped)
            self._events.emit(
                job="import",
                type="skipped",
                message=f"Already in the library, skipped: '{rec.name}'",
                album_id=rec.matched_album_id,
            )
            return

        self._repo.mark_import(import_id, ImportState.imported)
        self._events.emit(
            job="import",
            type="imported",
            message=f"Imported '{rec.name}'",
            album_id=rec.matched_album_id,
        )

        try:
            stager.finalize(rec)  # dispose the source; a hiccup here mustn't cause a re-import
        except Exception:
            log.warning("import %s: finalize/dispose failed", import_id, exc_info=True)

        self._claim_ownership(rec, new)

    def _album_ids(self) -> set[str]:
        return {a.beets_id for a in self._catalog.all_albums()} if self._catalog else set()

    def _new_albums(self, before: set[str]) -> list[BeetsAlbum]:
        if self._catalog is None:
            return []
        return [a for a in self._catalog.all_albums() if a.beets_id not in before]

    def _claim_ownership(self, rec: ImportRecord, new: list[BeetsAlbum]) -> None:
        """Turn a completed import into an owned album. A *matched* import already knows which
        album it is, so link it owned directly to the freshly-imported beets album — don't wait
        for reconcile, which keys on a MusicBrainz release-group that a quiet as-is beets import
        won't have attached. An *unmatched* import is reverse-matched against Spotify (D21).
        Best-effort: a failure here mustn't undo the successful import."""
        if self._catalog is None:
            return
        try:
            if rec.matched_album_id is not None:
                self._repo.mark_owned_manual(rec.matched_album_id, new[0].beets_id if new else None)
            elif self._reverse_matcher is not None:
                owned_ids = self._reverse_matcher.claim(new)
                if owned_ids:  # link the row to what it produced, so it isn't stuck at "no match"
                    self._repo.set_import_match(rec.id, owned_ids[0])
        except Exception:
            log.warning("import %s: ownership claim failed", rec.id, exc_info=True)

    def run_queued(self) -> int:
        """Process every queued import, one at a time (worker job). One failure never blocks the
        rest — the runner marks it failed; the operator can retry it from the Import screen."""
        # A worker crash mid-import leaves a row stuck at `importing`; requeue those first so
        # they retry. Safe because imports never run concurrently (scheduler max_instances=1).
        self._repo.requeue_importing()
        ids = self._repo.queued_import_ids()
        for import_id in ids:
            try:
                self.run(import_id)
            except Exception:
                pass  # run() already logged the traceback and recorded the error on the row
        return len(ids)


class ImportsService:
    """The Import worklist (§12/§13). Clicking Import just enqueues; the worker imports in the
    background so the operator can tick a batch and come back. Rows persist with their status."""

    def __init__(self, *, repo: AlbumRepo) -> None:
        self._repo = repo

    def pending(self) -> list[ImportItem]:
        """The Import worklist: downloads awaiting an Import/Discard decision (§12/§13)."""
        return [self._to_item(r) for r in self._repo.pending_imports()]

    def tasks(self, *, completed_window_days: int) -> list[ImportItem]:
        """The Tasks view: in-progress/queued/failed imports plus recently completed ones."""
        since = self._clock_now() - timedelta(days=completed_window_days)
        return [self._to_item(r) for r in self._repo.task_imports(since)]

    def archive(self) -> list[ImportItem]:
        """The completed archive: every finished import, however old."""
        return [self._to_item(r) for r in self._repo.completed_imports()]

    @staticmethod
    def _clock_now() -> datetime:
        return datetime.now(UTC)

    def _to_item(self, r: ImportRow) -> ImportItem:
        return ImportItem(
            id=r.id,
            source=r.source,
            name=r.name,
            media_kind=r.media_kind,
            import_target=r.import_target,
            classification_detail=r.classification_detail,
            destination_path=r.destination_path,
            state=r.state,
            matched_album_id=r.matched_album_id,
            matched=f"{r.matched_artist} — {r.matched_title}" if r.matched_album_id else None,
            matched_owned=r.matched_state == AlbumState.owned.value,
            missing=self._is_missing(r.state, r.archive_path),
            error_detail=r.error_detail,
            updated_at=r.updated_at,
            created_at=r.created_at,
        )

    @staticmethod
    def _is_missing(state: str, archive_path: str | None) -> bool:
        """A watch-dir drop whose file has since been removed (§13). Only meaningful before it's
        imported — an `imported` row's file is disposed on purpose; transmission rows have no
        local file to check (archive_path is None)."""
        checkable = (ImportState.detected.value, ImportState.failed.value)
        if archive_path is None or state not in checkable:
            return False
        return not Path(archive_path).exists()

    def enqueue(self, import_id: int) -> None:
        rec = self._repo.get_pending_import(import_id)
        if rec is None or rec.import_target == ImportTarget.review.value:
            return
        self._repo.queue_import(import_id)

    def reclassify(
        self,
        import_id: int,
        *,
        target: ImportTarget,
        tv_root: str,
        film_root: str,
        workspace_root: str,
    ) -> None:
        rec = self._repo.get_pending_import(import_id)
        if rec is None or rec.state not in (
            ImportState.detected.value,
            ImportState.queued.value,
            ImportState.failed.value,
        ):
            return
        classified = _manual_classification(
            rec.name,
            rec.files,
            target=target,
            tv_root=tv_root,
            film_root=film_root,
            workspace_root=workspace_root,
            matched_album_id=rec.matched_album_id,
        )
        self._repo.reclassify_import(
            import_id,
            media_kind=classified.media_kind,
            import_target=classified.import_target,
            classification_detail=classified.classification_detail,
            destination_path=classified.destination_path,
            state=ImportState.detected,
        )

    def discard(self, import_id: int) -> None:
        rec = self._repo.get_pending_import(import_id)
        # A discarded watch-dir drop shouldn't linger in the folder. A transmission row's source
        # lives on the seedbox and is never touched (seeding-safe, §12) — just dismiss it.
        if rec and rec.source == ImportSource.watchdir.value and rec.archive_path:
            path = Path(rec.archive_path)
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        self._repo.dismiss_import(import_id)


_AUDIO_EXTS = frozenset(
    {
        ".flac",
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".wav",
        ".aiff",
        ".aif",
        ".wma",
        ".alac",
        ".ape",
        ".wv",
        ".dsf",
        ".dff",
        ".mpc",
    }
)

_VIDEO_EXTS = frozenset(
    {
        ".mkv",
        ".mp4",
        ".avi",
        ".m4v",
        ".mov",
        ".wmv",
        ".mpg",
        ".mpeg",
        ".ts",
        ".m2ts",
        ".webm",
    }
)

_EPISODE_RE = re.compile(r"(?i)\bS(?P<season>\d{1,2})E(?P<episode>\d{2,3})\b")
_EPISODE_ALT_RE = re.compile(r"(?i)\b(?P<season>\d{1,2})x(?P<episode>\d{2,3})\b")
_SEASON_RE = re.compile(r"(?i)\bS(?:eason)?[ ._-]?(?P<season>\d{1,2})\b")
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_STRIP_TAIL_RE = re.compile(
    r"(?i)\b("
    r"720p|1080p|2160p|480p|x264|x265|h\.?264|h\.?265|hevc|bluray|bdrip|brrip|"
    r"webrip|web[- ]dl|amzn|nf|hulu|ddp?[57]\.1|aac2?\.0|proper|repack|remux|internal"
    r")\b.*$"
)


def _has_audio(files: list[str]) -> bool:
    """A torrent is music only if it carries at least one audio file — the filter that keeps
    a shared Transmission client's movies/software/ISOs out of the Import list (§12)."""
    return any(Path(f).suffix.lower() in _AUDIO_EXTS for f in files)


def _has_video(files: list[str]) -> bool:
    return any(Path(f).suffix.lower() in _VIDEO_EXTS for f in files)


def _classify_torrent(
    name: str,
    files: list[str],
    *,
    tv_root: str,
    film_root: str,
    workspace_root: str = "",
    matched_album_id: int | None,
) -> Classification:
    if _has_audio(files):
        return _music_classification(
            matched_album_id=matched_album_id,
            detail="Audio files detected.",
        )

    return _video_classification(
        name,
        files,
        tv_root=tv_root,
        film_root=film_root,
    )


def _manual_classification(
    name: str,
    files: list[str],
    *,
    target: ImportTarget,
    tv_root: str,
    film_root: str,
    workspace_root: str,
    matched_album_id: int | None,
) -> Classification:
    if target == ImportTarget.beets:
        return _music_classification(
            matched_album_id=matched_album_id,
            detail="Manual override: music import.",
        )
    if target == ImportTarget.workspace:
        return _workspace_classification(name, workspace_root)
    if target == ImportTarget.tv:
        classification = _tv_classification(name, files, tv_root)
        assert classification is not None
        return classification
    if target == ImportTarget.film:
        classification = _film_classification(name, files, film_root)
        assert classification is not None
        return classification
    raise ValueError(f"unsupported manual target: {target}")


def _music_classification(*, matched_album_id: int | None, detail: str) -> Classification:
    return Classification(
        media_kind=MediaKind.music,
        import_target=ImportTarget.beets,
        classification_detail=detail,
        destination_path=None,
        state=ImportState.detected,
        matched_album_id=matched_album_id,
    )


def _video_classification(
    name: str,
    files: list[str],
    *,
    tv_root: str,
    film_root: str,
) -> Classification:
    video_files = _video_files(files)
    if not video_files:
        return Classification(
            media_kind=MediaKind.unknown,
            import_target=ImportTarget.review,
            classification_detail="No audio or video files detected.",
            destination_path=None,
            state=ImportState.dismissed,
        )

    tv = _tv_classification(name, files, tv_root, auto=True)
    if tv is not None:
        return tv

    film = _film_classification(name, files, film_root, auto=True)
    if film is not None:
        return film

    return Classification(
        media_kind=MediaKind.unknown,
        import_target=ImportTarget.review,
        classification_detail="Video files found, but the title or type is ambiguous.",
        destination_path=None,
        state=ImportState.detected,
    )


@overload
def _tv_classification(
    name: str, files: list[str], tv_root: str, auto: Literal[False] = False
) -> Classification: ...


@overload
def _tv_classification(
    name: str, files: list[str], tv_root: str, auto: Literal[True]
) -> Classification | None: ...


def _tv_classification(
    name: str, files: list[str], tv_root: str, auto: bool = False
) -> Classification | None:
    video_files = _video_files(files)
    episode_matches = [_episode_match(p) for p in [name, *video_files]]
    episodes = [m for m in episode_matches if m is not None]
    if episodes:
        seasons = {season for _, season in episodes}
        show_title = _series_title(name, video_files)
        if show_title and len(seasons) == 1 and tv_root:
            season = next(iter(seasons))
            return Classification(
                media_kind=MediaKind.tv,
                import_target=ImportTarget.tv,
                classification_detail=(
                    f"Detected TV episode pack for season {season:02d}."
                    if auto
                    else f"Manual override: TV season pack for season {season:02d}."
                ),
                destination_path=str(Path(tv_root) / show_title / f"Season {season:02d}"),
                state=ImportState.detected,
            )
        detail = (
            "Detected TV episodes, but could not derive a single season destination."
            if auto
            else "Manual override requested TV, but no single season destination could be derived."
        )
        return Classification(
            media_kind=MediaKind.tv,
            import_target=ImportTarget.review,
            classification_detail=detail,
            destination_path=None,
            state=ImportState.detected,
        )
    if auto:
        return None
    return Classification(
        media_kind=MediaKind.tv,
        import_target=ImportTarget.review,
        classification_detail="Manual override requested TV, but no episodes were detected.",
        destination_path=None,
        state=ImportState.detected,
    )


@overload
def _film_classification(
    name: str, files: list[str], film_root: str, auto: Literal[False] = False
) -> Classification: ...


@overload
def _film_classification(
    name: str, files: list[str], film_root: str, auto: Literal[True]
) -> Classification | None: ...


def _film_classification(
    name: str, files: list[str], film_root: str, auto: bool = False
) -> Classification | None:
    video_files = _video_files(files)
    if not video_files:
        return None
    if not film_root:
        return Classification(
            media_kind=MediaKind.film,
            import_target=ImportTarget.review,
            classification_detail=(
                "Detected a film-like video, but the film root is not configured."
                if auto
                else "Manual override requested film, but the film root is not configured."
            ),
            destination_path=None,
            state=ImportState.detected,
        )
    main_videos = [vf for vf in video_files if "sample" not in Path(vf).stem.lower()]
    if len(main_videos) == 1:
        title, year = _film_title_and_year(name, main_videos[0])
        if title:
            folder = f"{title} ({year})" if year is not None else title
            detail = "Detected a single-feature film." if auto else "Manual override: film import."
            if year is None:
                detail = (
                    "Detected a film, but no year was found."
                    if auto
                    else "Manual override: film import (no year found)."
                )
            return Classification(
                media_kind=MediaKind.film,
                import_target=ImportTarget.film,
                classification_detail=detail,
                destination_path=str(Path(film_root) / folder),
                state=ImportState.detected,
            )
    if auto:
        return None
    return Classification(
        media_kind=MediaKind.film,
        import_target=ImportTarget.review,
        classification_detail="Manual override requested film, but the title is ambiguous.",
        destination_path=None,
        state=ImportState.detected,
    )


def _workspace_classification(
    name: str, workspace_root: str, detail: str = "Manual override: workspace import."
) -> Classification:
    if not workspace_root:
        return Classification(
            media_kind=MediaKind.workspace,
            import_target=ImportTarget.review,
            classification_detail=(
                "Manual override requested workspace, but the workspace root is not configured."
            ),
            destination_path=None,
            state=ImportState.detected,
        )
    folder = _clean_title(name) or "Import"
    return Classification(
        media_kind=MediaKind.workspace,
        import_target=ImportTarget.workspace,
        classification_detail=detail,
        destination_path=str(Path(workspace_root) / folder),
        state=ImportState.detected,
    )


_ERROR_DETAIL_CAP = 6000  # keep the stored log readable and the row small


def _error_detail(exc: BaseException) -> str:
    """A human-readable failure log for a failed import: the exception, the subprocess stderr if
    there is one (rsync/beets put the real reason there), then the traceback. Capped in length."""
    parts = [f"{type(exc).__name__}: {exc}"]
    stderr = getattr(exc, "stderr", None)  # CalledProcessError from rsync/beet carries the reason
    if stderr:
        text = stderr.decode(errors="replace") if isinstance(stderr, bytes) else str(stderr)
        if text.strip():
            parts.append(f"\nstderr:\n{text.strip()}")
    parts.append("\n" + "".join(traceback.format_exception(exc)))
    return "\n".join(parts)[:_ERROR_DETAIL_CAP]


def _match_targets(repo: AlbumRepo) -> list[MatchTarget]:
    return [
        MatchTarget(id=c.id, artist=c.artist, title=c.title) for c in repo.albums_for_matching()
    ]


def _drop_key(drop: Path) -> str:
    """Idempotency key for a watch-dir drop: path + a cheap content signature (size+mtime),
    so re-scans don't reprocess but a genuinely changed file would be picked up."""
    st = drop.stat()
    return (
        f"{drop.resolve()}:{_dir_size(drop)}:{int(st.st_mtime)}"
        if drop.is_dir()
        else (f"{drop.resolve()}:{st.st_size}:{int(st.st_mtime)}")
    )


def _newest_mtime(entry: Path) -> datetime:
    if entry.is_file():
        return datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
    mtimes = [p.stat().st_mtime for p in entry.rglob("*") if p.is_file()]
    newest = max(mtimes, default=entry.stat().st_mtime)
    return datetime.fromtimestamp(newest, tz=UTC)


def _dir_size(entry: Path) -> int:
    return sum(p.stat().st_size for p in entry.rglob("*") if p.is_file())


def _dir_has_audio(entry: Path) -> bool:
    return any(_has_audio([str(p)]) for p in entry.rglob("*") if p.is_file())


def _video_files(files: list[str]) -> list[str]:
    return [f for f in files if Path(f).suffix.lower() in _VIDEO_EXTS]


def _episode_match(value: str) -> tuple[str, int] | None:
    # Match the basename only. A torrent's file entries are paths relative to the release folder
    # (e.g. "Show.S02.Complete.1080p.JUNK/Show.S02E01.mkv"); taking "text before SxxEyy" from the
    # whole path would fold the folder's season/quality tags into the show title.
    cleaned = Path(value).name.replace("_", " ").replace(".", " ")
    for pattern in (_EPISODE_RE, _EPISODE_ALT_RE):
        match = pattern.search(cleaned)
        if match:
            prefix = cleaned[: match.start()].strip(" -._")
            return prefix, int(match.group("season"))
    return None


def _series_title(name: str, files: list[str]) -> str | None:
    candidates = [name, *files]
    for value in candidates:
        match = _episode_match(value)
        if match is not None:
            title = _clean_title(match[0])
            if title:
                return title
    season_match = _SEASON_RE.search(name.replace(".", " ").replace("_", " "))
    if season_match:
        title = _clean_title(name[: season_match.start()])
        if title:
            return title
    return None


def _film_title_and_year(name: str, main_video: str) -> tuple[str | None, int | None]:
    candidates = [Path(main_video).stem, Path(main_video).parent.name, name]
    for raw in candidates:
        cleaned = raw.replace(".", " ").replace("_", " ")
        year_match = _YEAR_RE.search(cleaned)
        if year_match:
            title = _clean_title(cleaned[: year_match.start()])
            if title:
                return title, int(year_match.group(1))
    for raw in candidates:
        title = _clean_title(raw)
        if title:
            return title, None
    return None, None


def _clean_title(raw: str) -> str | None:
    # These titles come from untrusted torrent names and are used to build filesystem destinations
    # under tv_root/film_root, so neutralise path separators and NULs up front — otherwise a
    # crafted name yielding e.g. a leading-slash segment makes `Path(root) / seg` discard the root
    # entirely (path escape). `.` becomes a space below, so `..` traversal can't survive either.
    title = raw.replace("/", " ").replace("\\", " ").replace("\x00", " ")
    title = title.replace(".", " ").replace("_", " ").strip()
    title = _STRIP_TAIL_RE.sub("", title)
    title = re.sub(r"\s+", " ", title).strip(" -._")
    if not title:
        return None
    return " ".join(word.capitalize() if word.islower() else word for word in title.split())


def _content_root(staging: Path) -> Path:
    children = list(staging.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return staging


def _move_into(source: Path, dest: Path) -> int:
    """Move `source` to `dest`, returning how many files were actually placed. A file already at
    the destination is left untouched (skipped, not overwritten) so a re-import can't clobber the
    library or fail the whole pack on one pre-existing episode."""
    if source.is_dir():
        if dest.exists() and not dest.is_dir():
            raise FileExistsError(f"destination exists and is not a directory: {dest}")
        dest.mkdir(parents=True, exist_ok=True)
        moved = sum(_move_into(child, dest / child.name) for child in source.iterdir())
        # Only removable once emptied; if some children were skipped it stays, which is fine.
        try:
            source.rmdir()
        except OSError:
            pass
        return moved
    if dest.exists():
        if source.stat().st_size == dest.stat().st_size:
            return 0  # already in the library — skip, don't overwrite
        raise FileExistsError(
            f"destination exists with a different size: {dest} "
            f"(source={source.stat().st_size}, destination={dest.stat().st_size})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(source, dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        tmp = dest.with_name(f".{dest.name}.tmp-{os.getpid()}")
        try:
            shutil.copy2(source, tmp)
            os.replace(tmp, dest)
            source.unlink()
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    return 1
