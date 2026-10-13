from typing import Protocol


class EventSink(Protocol):
    """Where the application records item-level activity (SPEC §16 / activity feed). One row
    per meaningful step — "resolved X", "X now owned", "importing X" — not per network call.

    Written from the worker and from the API both: the feed is one log for the application,
    and a thing the operator did is as much a part of what happened as a poll is."""

    def emit(self, *, job: str, type: str, message: str, album_id: int | None = None) -> None: ...
