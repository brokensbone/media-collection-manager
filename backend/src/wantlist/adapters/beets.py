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
    """The beets CLI seam (SPEC §5) — the ONLY place we touch beets. beets is bundled, so
    we run `beet` directly; the config points at the mounted library. Never raw SQLite."""

    def __init__(self, config: str | None = None) -> None:
        self._config = config

    def owned_release_group_ids(self) -> set[str]:
        out = subprocess.run(
            [*self._argv, "list", "-a", "-f", "$mb_releasegroupid"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout
        return {line.strip() for line in out.splitlines() if line.strip()}

    def all_albums(self) -> list[BeetsAlbum]:
        """Every album in the library as (id, artist, title, rgid) — the catalogue behind the
        D17 link-candidate suggestions and the "possibly already owned?" hint (§5/§7)."""
        fmt = _SEP.join(["$id", "$albumartist", "$album", "$mb_releasegroupid"])
        out = subprocess.run(
            [*self._argv, "list", "-a", "-f", fmt],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout
        albums = []
        for line in out.splitlines():
            if not line.strip():
                continue
            beets_id, artist, title, rgid = line.split(_SEP)
            albums.append(BeetsAlbum(beets_id, artist, title, rgid or None))
        return albums

    def import_dir(self, path: str) -> None:
        """Import a folder into the library non-interactively (SPEC §12/§13). beets moves
        the files into the library per its config (`move: yes`), leaving the inbox empty."""
        subprocess.run(
            [*self._argv, "import", "-q", path],
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )

    @property
    def _argv(self) -> list[str]:
        return ["beet", *(["-c", self._config] if self._config else [])]
