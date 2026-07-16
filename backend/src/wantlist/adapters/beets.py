import subprocess


class BeetsClient:
    """The beets CLI seam (SPEC §5) — the ONLY place we touch beets. beets is bundled, so
    we run `beet` directly; the config points at the mounted library. Never raw SQLite."""

    def __init__(self, config: str | None = None) -> None:
        self._config = config

    def owned_release_group_ids(self) -> set[str]:
        argv = ["beet"]
        if self._config:
            argv += ["-c", self._config]
        argv += ["list", "-a", "-f", "$mb_releasegroupid"]
        out = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=120).stdout
        return {line.strip() for line in out.splitlines() if line.strip()}
