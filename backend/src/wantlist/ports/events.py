from typing import Protocol


class EventSink(Protocol):
    """Where the worker records item-level activity (SPEC §16 / activity feed). One row per
    meaningful step — "resolved X", "X now owned", "importing X" — not per network call."""

    def emit(self, *, job: str, type: str, message: str, album_id: int | None = None) -> None: ...
