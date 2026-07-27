import subprocess
from pathlib import Path


class RsyncTransfer:
    """Pulls a torrent's files off the seedbox with rsync-over-SSH (SPEC §12). Copies only —
    never `--remove-source-files` or `--delete` — so the seedbox originals (and seeding) are
    untouched. `--files-from` reads the exact file list on stdin, relative to `download_dir`,
    so single-file, multi-file and mixed torrents all transfer precisely."""

    def __init__(
        self, *, host: str, port: int, user: str, ssh_key: str, transfer_timeout: int = 1800
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._ssh_key = ssh_key
        self._transfer_timeout = transfer_timeout

    def test(self) -> None:
        """Open an SSH session to the seedbox and run `true` — the Transmission page's SSH
        connection check. Same options as fetch() so it exercises the real auth path. Raises
        CalledProcessError (with stderr) or TimeoutExpired on failure."""
        argv = [
            "ssh",
            "-p",
            str(self._port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
        ]
        if self._ssh_key:
            argv += ["-i", self._ssh_key]
        argv += [f"{self._user}@{self._host}", "true"]
        subprocess.run(argv, capture_output=True, text=True, check=True, timeout=20)

    def fetch(self, *, download_dir: str, files: list[str], dest: str) -> None:
        Path(dest).mkdir(parents=True, exist_ok=True)
        # BatchMode: never prompt (fail fast instead of hanging). accept-new: trust the
        # seedbox host key on first use but still detect a later key change (§12, runs headless).
        ssh = f"ssh -p {self._port} -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
        if self._ssh_key:
            ssh += f" -i {self._ssh_key}"
        source = f"{self._user}@{self._host}:{download_dir.rstrip('/')}/"
        argv = ["rsync", "-a", "-e", ssh, "--files-from=-", source, f"{dest.rstrip('/')}/"]
        subprocess.run(
            argv,
            input="\n".join(files),
            text=True,
            capture_output=True,
            check=True,
            timeout=self._transfer_timeout,
        )
