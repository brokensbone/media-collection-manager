import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

_SEP = "\x1f"  # unit separator: safe field delimiter (won't occur in artist/album text)
_LOCK_RETRIES = 4
_LOCK_BACKOFF = 1.5  # seconds; grows per attempt


@dataclass
class BeetsAlbum:
    beets_id: str
    artist: str
    title: str
    mb_releasegroup_id: str | None


class BeetsClient:
    """The beets CLI seam (SPEC §5) — the ONLY place we touch beets. beets is bundled, so we run
    `beet` directly. It reads `BEETSDIR` from the environment (set by the deploy to the beets
    directory) to find its config.yaml and, via that config, the library.db + music. Never raw
    SQLite. Relative library/directory paths in the config resolve against BEETSDIR, so pointing
    BEETSDIR at the mounted library dir is all that's needed."""

    def owned_release_group_ids(self) -> set[str]:
        out = self._run("list", "-a", "-f", "$mb_releasegroupid", timeout=120)
        return {line.strip() for line in out.splitlines() if line.strip()}

    def all_albums(self) -> list[BeetsAlbum]:
        """Every album in the library as (id, artist, title, rgid) — the catalogue behind the
        D17 link-candidate suggestions and the "possibly already owned?" hint (§5/§7)."""
        fmt = _SEP.join(["$id", "$albumartist", "$album", "$mb_releasegroupid"])
        albums = []
        for line in self._run("list", "-a", "-f", fmt, timeout=120).splitlines():
            if not line.strip():
                continue
            beets_id, artist, title, rgid = line.split(_SEP)
            albums.append(BeetsAlbum(beets_id, artist, title, rgid or None))
        return albums

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
            ov.write("import:\n    duplicate_action: skip\n")
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
