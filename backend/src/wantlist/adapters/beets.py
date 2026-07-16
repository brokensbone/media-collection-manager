import shlex
import subprocess


class BeetsClient:
    """The beets CLI seam (SPEC §5) — the ONLY place we touch beets. Command is configurable
    (`beet`, `docker exec … beet`, `ssh … beet`), never raw SQLite (which locked constantly)."""

    def __init__(self, command: str, config: str | None = None) -> None:
        self._command = command
        self._config = config

    def owned_release_group_ids(self) -> set[str]:
        argv = shlex.split(self._command)
        if self._config:
            argv += ["-c", self._config]
        argv += ["list", "-a", "-f", "$mb_releasegroupid"]
        out = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=120).stdout
        return {line.strip() for line in out.splitlines() if line.strip()}
