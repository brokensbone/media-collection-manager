import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from .adapters.album_repo import AlbumRepo, ImportRecord
from .adapters.beets import BeetsAlbum
from .adapters.unpack import dispose, unpack
from .domain.match import MatchTarget, best_match
from .models import ImportSource, ImportState
from .ports.clock import Clock
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
    state: str  # detected | queued | imported | failed — drives the status shown per row
    matched_album_id: int | None
    matched: str | None  # "Artist — Title" of the matched want, or None for the no-match tail


# --- detection: one service per front (§12 Transmission / §13 watch-dir) --------------


class ImportDetectionService:
    """Polls Transmission for completed downloads, records each once (hash ledger), and
    fuzzy-matches it to a wanted album (SPEC §12). Unmatched downloads are still recorded
    so the operator can hand-import them (the no-match tail)."""

    def __init__(
        self, *, transmission: TransmissionClient, repo: AlbumRepo, match_threshold: float
    ):
        self._transmission = transmission
        self._repo = repo
        self._threshold = match_threshold

    def poll(self) -> DetectResult:
        known = self._repo.known_source_keys()
        fresh = [t for t in self._transmission.completed_torrents() if t.hash not in known]
        if not fresh:
            return DetectResult(detected=0)

        targets = _match_targets(self._repo)
        for t in fresh:
            self._repo.add_pending_import(
                source=ImportSource.transmission,
                source_key=t.hash,
                name=t.name,
                download_dir=t.download_dir,
                files=t.files,
                matched_album_id=best_match(t.name, targets, self._threshold),
            )
        return DetectResult(detected=len(fresh))


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
    ):
        self._repo = repo
        self._tags = tags
        self._clock = clock
        self._watch_dir = watch_dir
        self._archive_subdir = archive_subdir
        self._settle_seconds = settle_seconds
        self._threshold = match_threshold

    def poll(self) -> DetectResult:
        root = Path(self._watch_dir)
        if not root.is_dir():
            return DetectResult(detected=0)

        known = self._repo.known_source_keys()
        cutoff = self._clock.now() - timedelta(seconds=self._settle_seconds)
        fresh = [drop for drop in self._settled_drops(root, cutoff) if _drop_key(drop) not in known]
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
                archive_path=str(drop),
                matched_album_id=best_match(query, targets, self._threshold),
            )
        return DetectResult(detected=len(fresh))

    def _settled_drops(self, root: Path, cutoff: datetime) -> list[Path]:
        drops = []
        for entry in sorted(root.iterdir()):
            if entry.name == self._archive_subdir:
                continue  # never re-ingest what we archived
            if entry.is_file() and entry.suffix.lower() != ".zip":
                continue
            if _newest_mtime(entry) <= cutoff:  # settle check: not still being written
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
        inbox: str,
        catalog: LibraryCatalog | None = None,
        reverse_matcher: ReverseMatcher | None = None,
    ):
        self._repo = repo
        self._stagers = stagers
        self._beets = beets
        self._inbox = inbox
        self._catalog = catalog
        self._reverse_matcher = reverse_matcher

    def run(self, import_id: int) -> None:
        rec = self._repo.get_pending_import(import_id)
        if rec is None or rec.state != ImportState.queued.value:
            return  # only queued imports are processed (the click/retry enqueues them)
        stager = self._stagers[ImportSource(rec.source)]

        before = self._album_ids()  # snapshot to identify what this import adds (D21)
        staging = Path(self._inbox) / str(rec.id)  # unique per import; no name-collisions
        try:
            stager.stage(rec, str(staging))
            self._beets.import_dir(str(staging))
        except Exception:
            self._repo.mark_import(import_id, ImportState.failed)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)  # tidy the local staging either way
        self._repo.mark_import(import_id, ImportState.imported)

        try:
            stager.finalize(rec)  # dispose the source; a hiccup here mustn't cause a re-import
        except Exception:
            log.warning("import %s: finalize/dispose failed", import_id, exc_info=True)

        self._reverse_match(rec, before)

    def _album_ids(self) -> set[str]:
        return {a.beets_id for a in self._catalog.all_albums()} if self._catalog else set()

    def _reverse_match(self, rec: ImportRecord, before: set[str]) -> None:
        # Only an *unmatched* import needs this — a matched one flips its want to owned via
        # reconcile. Best-effort: a failure here mustn't undo a successful import.
        if self._reverse_matcher is None or self._catalog is None:
            return
        if rec.matched_album_id is not None:
            return
        try:
            new = [a for a in self._catalog.all_albums() if a.beets_id not in before]
            self._reverse_matcher.claim(new)
        except Exception:
            log.warning("import %s: reverse-match failed", rec.id, exc_info=True)

    def run_queued(self) -> int:
        """Process every queued import (worker job). One failure never blocks the rest — the
        runner marks it failed; the operator can retry it from the Import screen."""
        ids = self._repo.queued_import_ids()
        for import_id in ids:
            try:
                self.run(import_id)
            except Exception:
                log.warning("import %s failed", import_id)  # already marked failed in run()
        return len(ids)


class ImportsService:
    """The Import worklist (§12/§13). Clicking Import just enqueues; the worker imports in the
    background so the operator can tick a batch and come back. Rows persist with their status."""

    def __init__(self, *, repo: AlbumRepo) -> None:
        self._repo = repo

    def queue(self) -> list[ImportItem]:
        return [
            ImportItem(
                id=r.id,
                source=r.source,
                name=r.name,
                state=r.state,
                matched_album_id=r.matched_album_id,
                matched=f"{r.matched_artist} — {r.matched_title}" if r.matched_album_id else None,
            )
            for r in self._repo.list_imports()
        ]

    def enqueue(self, import_id: int) -> None:
        self._repo.queue_import(import_id)


def _match_targets(repo: AlbumRepo) -> list[MatchTarget]:
    return [
        MatchTarget(id=c.id, artist=c.artist, title=c.title)
        for c in repo.albums_for_matching()
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
