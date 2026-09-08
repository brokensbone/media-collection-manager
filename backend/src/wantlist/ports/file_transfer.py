from typing import Protocol


class FileTransfer(Protocol):
    """Pulls a completed download's files off the seedbox into local staging (SPEC §12).
    Implementations must COPY, never move/delete the source, so seeding is never disturbed."""

    def fetch(self, *, download_dir: str, files: list[str], dest: str) -> None: ...
