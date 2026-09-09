from typing import Protocol


class MusicBrainzResolver(Protocol):
    """Resolves a Spotify album to a MusicBrainz release-group id (SPEC §5).
    Returns None when unresolvable (the ~14% MB-absent tail, §11)."""

    def resolve(
        self, *, upc: str | None, isrcs: list[str], artist: str, title: str
    ) -> str | None: ...
