import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath

log = logging.getLogger(__name__)

_SEP = "\x1f"  # unit separator: safe field delimiter (won't occur in artist/album text)
_LOCK_RETRIES = 4
_LOCK_BACKOFF = 1.5  # seconds; grows per attempt


def _year(raw: str) -> int | None:
    """beets prints `0` (or blank) for an album with no year — treat both as absent."""
    raw = raw.strip()
    return int(raw) if raw.isdigit() and raw != "0" else None


def _facet(raw: str) -> str | None:
    """A curation-facet field value, or None when absent. beets emits the literal template token
    (e.g. `$media`) for a field it can't resolve on an album — not an empty string — so a leaked
    `$…` token must be treated as absent too, or it becomes a bogus "$media" crate."""
    raw = raw.strip()
    return None if not raw or raw.startswith("$") else raw


def _added(raw: str) -> datetime | None:
    """Parse Beets's epoch or human-formatted `added` value."""
    value = raw.strip()
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (OSError, OverflowError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _duration_seconds(raw: str) -> float | None:
    """Parse Beets's numeric or human-formatted ``$length`` value.

    Beets formats whole-second lengths as ``M:SS`` (and long items as
    ``H:MM:SS``) in the CLI, despite the field being numeric in its database.
    A malformed optional duration must not prevent the worker from refreshing
    otherwise playable paths.
    """
    value = raw.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    parts = value.split(":")
    if len(parts) not in {2, 3} or any(not part.isdigit() for part in parts[:-1]):
        return None
    try:
        tail = float(parts[-1])
    except ValueError:
        return None
    if tail < 0:
        return None
    return tail + sum(int(part) * 60**place for place, part in enumerate(reversed(parts[:-1]), 1))


@dataclass
class BeetsAlbum:
    beets_id: str
    artist: str
    title: str
    mb_releasegroup_id: str | None
    # Curation facets (crates §1): surfaced read-only for the boxes feature's future split
    # suggestions. `secondary_types` is beets' `$albumtypes` verbatim (primary + secondary, e.g.
    # "album; compilation"); the rest map 1:1 to beets fields. All optional — beets emits an
    # empty field when a value is absent, and much of a personal library will lack labels/country.
    year: int | None = None
    media: str | None = None  # physical/source format: CD, "12\" Vinyl", Digital Media, …
    label: str | None = None
    country: str | None = None
    secondary_types: str | None = None  # beets $albumtypes (raw); MB secondary types live here
    genre: str | None = None
    added_at: datetime | None = None


@dataclass
class BeetsTrack:
    beets_id: str
    item_id: str
    disc: int | None
    track: int | None
    title: str
    duration_seconds: float | None
    path: str


class BeetsClient:
    """The beets CLI seam (SPEC §5) — the ONLY place we touch beets. beets is bundled, so we run
    `beet` directly. It reads `BEETSDIR` from the environment (set by the deploy to the beets
    directory) to find its config.yaml and, via that config, the library.db + music. Never raw
    SQLite. Relative library/directory paths in the config resolve against BEETSDIR, so pointing
    BEETSDIR at the mounted library dir is all that's needed."""

    def __init__(self, *, import_directory: str = "") -> None:
        self._import_directory = import_directory

    def owned_release_group_ids(self) -> set[str]:
        out = self._run("list", "-a", "-f", "$mb_releasegroupid", timeout=120)
        return {line.strip() for line in out.splitlines() if line.strip()}

    # beets format fields dumped per album, in BeetsAlbum's field order. `$albumtypes` carries the
    # MB secondary types (crates §1); the rest map straight onto BeetsAlbum.
    _ALBUM_FIELDS = (  # noqa: RUF012 (a fixed field spec, not mutable shared state)
        "$id",
        "$albumartist",
        "$album",
        "$mb_releasegroupid",
        "$year",
        "$media",
        "$label",
        "$country",
        "$albumtypes",
        "$genre",
        "$added",
    )

    def all_albums(self) -> list[BeetsAlbum]:
        """Every album in the library — the catalogue behind the D17 link-candidate suggestions,
        the "possibly already owned?" hint (§5/§7), and the crates facets (§1). Curation facets
        (year, format, label, country, secondary types, genre) ride along read-only."""
        fmt = _SEP.join(self._ALBUM_FIELDS)
        albums = []
        for line in self._run("list", "-a", "-f", fmt, timeout=120).splitlines():
            if not line.strip():
                continue
            bid, artist, title, rgid, year, media, label, country, types, genre, added = line.split(
                _SEP
            )
            albums.append(
                BeetsAlbum(
                    beets_id=bid,
                    artist=artist,
                    title=title,
                    mb_releasegroup_id=rgid or None,
                    year=_year(year),
                    media=_facet(media),
                    label=_facet(label),
                    country=_facet(country),
                    secondary_types=_facet(types),
                    genre=_facet(genre),
                    added_at=_added(added),
                )
            )
        return albums

    _TRACK_FIELDS = ("$album_id", "$id", "$disc", "$track", "$title", "$length", "$path")

    def all_tracks(
        self, *, music_directory: str, legacy_music_directory: str = ""
    ) -> list[BeetsTrack]:
        """Dump playable item data once per worker refresh.

        MCM stores paths relative to MPD's music root.  That keeps the radio API useful to MPD
        without disclosing the worker's filesystem layout or giving callers Beets access.
        """
        root = PurePath(music_directory)
        legacy_root = PurePath(legacy_music_directory) if legacy_music_directory else None
        tracks: list[BeetsTrack] = []
        output = self._run("list", "-f", _SEP.join(self._TRACK_FIELDS), timeout=120)
        for line in output.splitlines():
            if not line.strip():
                continue
            album_id, item_id, disc, track, title, length, path = line.split(_SEP)
            item_path = PurePath(path)
            relative = _relative_music_path(item_path, root, legacy_root)
            if relative is None:
                log.warning("excluding Beets item outside music directory: %s", path)
                continue
            tracks.append(
                BeetsTrack(
                    beets_id=album_id,
                    item_id=item_id,
                    disc=int(disc) if disc.isdigit() and disc != "0" else None,
                    track=int(track) if track.isdigit() and track != "0" else None,
                    title=title,
                    duration_seconds=_duration_seconds(length),
                    path=str(relative),
                )
            )
        return tracks

    def import_dir(self, path: str) -> None:
        """Import a folder into the library non-interactively (SPEC §12/§13), leaving the inbox
        empty. Force `duplicate_action: skip` so importing an album already in the library never
        keeps a second copy — the deploy's config left it at beets' default ("keep" in quiet
        mode). We layer it via `--config`, which merges over BEETSDIR's config without disturbing
        its library/directory paths, so it holds regardless of what the deploy's config sets.
        `--quiet-fallback=asis` still lets a genuinely new but un-tagged album import as-is.

        `-vv` is a diagnostic trap (see `_trap_import_directory`): it makes beets log the config
        and library paths it actually resolved for THIS invocation, which we then record."""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as ov:
            # JSON is also valid YAML, avoiding unsafe interpolation for paths with spaces or
            # punctuation. This overlay has higher priority than the migrated config.yaml.
            override: dict[str, object] = {"import": {"duplicate_action": "skip"}}
            if self._import_directory:
                override["directory"] = self._import_directory
            ov.write(json.dumps(override))
            overrides = ov.name
        try:
            result = self._run_result(
                "-vv",
                "--config",
                overrides,
                "import",
                "-q",
                "--quiet-fallback=asis",
                path,
                timeout=600,
            )
        finally:
            os.unlink(overrides)
        self._trap_import_directory(path, result.stderr)

    def _trap_import_directory(self, path: str, stderr: str) -> None:
        """Diagnostic trap: imports have intermittently landed under beets' DEFAULT directory
        (`~/Music` → `/root/Music` in the container) instead of the configured `directory:`,
        leaving phantom paths. It has not reproduced on demand, so instead of guessing we record
        what every import actually resolved. `beet -vv` logs three lines to stderr — `data
        directory:` (where beets loaded config from, i.e. BEETSDIR), `library database:` and
        `library directory:` (where it writes files). We surface them for every import and shout
        if the library directory is the default, so the next recurrence self-reports the exact
        broken state (BEETSDIR unset? config unreadable?). Remove once the cause is pinned."""
        resolved = {
            key: line.split(":", 1)[1].strip()
            for line in stderr.splitlines()
            for key in ("data directory", "library database", "library directory")
            if line.strip().startswith(f"{key}:")
        }
        home = os.environ.get("HOME", "")
        default_dir = os.path.join(home, "Music") if home else "/root/Music"
        context = (
            f"path={path!r} BEETSDIR={os.environ.get('BEETSDIR', '')!r} HOME={home!r} "
            f"cwd={os.getcwd()!r} resolved={resolved!r}"
        )
        library_dir = resolved.get("library directory", "")
        if not library_dir or library_dir == default_dir or library_dir.startswith("/root/Music"):
            log.warning("beets import used the DEFAULT (wrong) library directory — %s", context)
        else:
            log.info("beets import directory ok — %s", context)

    def _run(self, *args: str, timeout: int) -> str:
        return self._run_result(*args, timeout=timeout).stdout

    def _run_result(self, *args: str, timeout: int) -> "subprocess.CompletedProcess[str]":
        # No env= override: inherit the process environment so `beet` picks up BEETSDIR.
        #
        # beets keeps its catalogue in one SQLite file shared across this worker and the API
        # process (Owned view, health check) plus reconcile — so a concurrent writer/reader can
        # hold the lock past beets' busy timeout and the call dies with "database is locked".
        # Retry with backoff: the contending call is short-lived, so a retry clears it. (beets'
        # own `timeout:` config raises the busy timeout too, but this keeps us safe without it.)
        for attempt in range(_LOCK_RETRIES + 1):
            try:
                return subprocess.run(
                    ["beet", *args], capture_output=True, text=True, check=True, timeout=timeout
                )
            except subprocess.CalledProcessError as e:
                if attempt < _LOCK_RETRIES and "database is locked" in (e.stderr or ""):
                    time.sleep(_LOCK_BACKOFF * (attempt + 1))
                    continue
                raise
        raise RuntimeError("unreachable: the retry loop returns or raises")


def _relative_music_path(
    item_path: PurePath, music_root: PurePath, legacy_music_root: PurePath | None
) -> PurePath | None:
    """Return an MPD-relative item path, including an explicitly configured legacy mapping."""
    try:
        return item_path.relative_to(music_root)
    except ValueError:
        pass
    if legacy_music_root is not None:
        try:
            relative = item_path.relative_to(legacy_music_root)
        except ValueError:
            pass
        else:
            log.info("remapping legacy Beets music path to MPD root: %s", item_path)
            return relative
    return None
