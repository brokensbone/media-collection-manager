from pathlib import Path
from typing import Protocol


class TagReader(Protocol):
    """Reads (artist, album) from a watch-dir drop's embedded audio tags (SPEC §13) — a
    better match signal than the filename. Returns None when no tags can be read."""

    def read(self, path: Path) -> tuple[str, str] | None: ...
