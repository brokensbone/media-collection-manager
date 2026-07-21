import subprocess
from dataclasses import dataclass

_SEP = "\x1f"  # unit separator: safe field delimiter (won't occur in artist/album text)


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
        """Import a folder into the library non-interactively (SPEC §12/§13). beets moves the
        files into the library per its config (`move: yes`), leaving the inbox empty."""
        self._run("import", "-q", path, timeout=600)

    def _run(self, *args: str, timeout: int) -> str:
        # No env= override: inherit the process environment so `beet` picks up BEETSDIR.
        return subprocess.run(
            ["beet", *args], capture_output=True, text=True, check=True, timeout=timeout
        ).stdout
