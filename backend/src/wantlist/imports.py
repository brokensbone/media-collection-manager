import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .adapters.album_repo import AlbumRepo
from .domain.match import MatchTarget, best_match
from .models import ImportState
from .ports.transmission import TransmissionClient


class BeetsImporter(Protocol):
    """The beets import seam we depend on (a subset of BeetsClient, SPEC §5/§12)."""

    def import_dir(self, path: str) -> None: ...


@dataclass
class DetectResult:
    detected: int


@dataclass
class ImportItem:
    id: int
    name: str
    matched_album_id: int | None
    matched: str | None  # "Artist — Title" of the matched want, or None for the no-match tail


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
        known = self._repo.known_torrent_hashes()
        fresh = [t for t in self._transmission.completed_torrents() if t.hash not in known]
        if not fresh:
            return DetectResult(detected=0)

        targets = [
            MatchTarget(id=w.id, artist=w.artist, title=w.title)
            for w in self._repo.wanted_for_matching()
        ]
        for t in fresh:
            self._repo.add_download_import(
                torrent_hash=t.hash,
                name=t.name,
                download_dir=t.download_dir,
                files=t.files,
                matched_album_id=best_match(t.name, targets, self._threshold),
            )
        return DetectResult(detected=len(fresh))


class ImportRunner:
    """Copies a completed download into the beets inbox (never moving the seedbox originals,
    so seeding is never disturbed — SPEC §12), imports it into beets, and tidies the staging
    copy. Ownership then flips to `owned` on the next reconcile via the release-group match."""

    def __init__(self, *, repo: AlbumRepo, beets: BeetsImporter, inbox: str):
        self._repo = repo
        self._beets = beets
        self._inbox = inbox

    def run(self, import_id: int) -> None:
        rec = self._repo.get_download_import(import_id)
        if rec is None or rec.state != ImportState.detected.value:
            return

        staging = Path(self._inbox) / Path(rec.download_dir).name
        try:
            self._copy_in(rec.download_dir, rec.files, staging)
            self._beets.import_dir(str(staging))
        except Exception:
            self._repo.mark_import(import_id, ImportState.failed)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)  # tidy the staging copy either way
        self._repo.mark_import(import_id, ImportState.imported)

    @staticmethod
    def _copy_in(download_dir: str, files: list[str], staging: Path) -> None:
        staging.mkdir(parents=True, exist_ok=True)
        for rel in files:
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(download_dir) / rel, dest)


class ImportsService:
    """The Import worklist (§12): detected downloads awaiting a one-click import."""

    def __init__(self, *, repo: AlbumRepo, runner: ImportRunner):
        self._repo = repo
        self._runner = runner

    def queue(self) -> list[ImportItem]:
        return [
            ImportItem(
                id=r.id,
                name=r.name,
                matched_album_id=r.matched_album_id,
                matched=f"{r.matched_artist} — {r.matched_title}" if r.matched_album_id else None,
            )
            for r in self._repo.pending_imports()
        ]

    def run_import(self, import_id: int) -> None:
        self._runner.run(import_id)
