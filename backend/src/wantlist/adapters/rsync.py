import subprocess
from pathlib import Path


class RsyncTransfer:
    """Pulls a torrent's files off the seedbox with rsync-over-SSH (SPEC §12). Copies only —
    never `--remove-source-files` or `--delete` — so the seedbox originals (and seeding) are
    untouched. `--files-from` reads the exact file list on stdin, relative to `download_dir`,
    so single-file, multi-file and mixed torrents all transfer precisely."""

    def __init__(self, *, host: str, port: int, user: str, ssh_key: str) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._ssh_key = ssh_key

    def fetch(self, *, download_dir: str, files: list[str], dest: str) -> None:
        Path(dest).mkdir(parents=True, exist_ok=True)
        ssh = f"ssh -p {self._port}" + (f" -i {self._ssh_key}" if self._ssh_key else "")
        source = f"{self._user}@{self._host}:{download_dir.rstrip('/')}/"
        argv = ["rsync", "-a", "-e", ssh, "--files-from=-", source, f"{dest.rstrip('/')}/"]
        subprocess.run(
            argv, input="\n".join(files), text=True, capture_output=True, check=True, timeout=1800
        )
