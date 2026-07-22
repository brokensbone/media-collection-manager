import logging
from dataclasses import dataclass
from typing import Protocol

from .adapters.album_repo import AlbumRepo
from .adapters.event_log import NullEventSink
from .ports.events import EventSink

log = logging.getLogger(__name__)


class OwnedReleaseGroups(Protocol):
    def owned_release_group_ids(self) -> set[str]: ...


@dataclass
class ReconcileResult:
    newly_owned: int


class OwnershipReconciler:
    """The deterministic ownership join (§5): one beets dump → in-memory diff → mark owned.
    Never touches manual links (owned by the human, §4)."""

    def __init__(
        self, *, beets: OwnedReleaseGroups, repo: AlbumRepo, events: EventSink | None = None
    ) -> None:
        self._beets = beets
        self._repo = repo
        self._events = events or NullEventSink()

    def reconcile(self) -> ReconcileResult:
        owned = self._beets.owned_release_group_ids()
        to_own = [aid for aid, rgid in self._repo.resolvable_unowned() if rgid in owned]
        self._repo.mark_owned_auto(to_own)
        if to_own:
            labels = self._repo.labels_for(to_own)
            for aid in to_own:
                self._events.emit(
                    job="reconcile",
                    type="owned",
                    message=f"In your library — now owned: '{labels.get(aid, str(aid))}'",
                    album_id=aid,
                )
        return ReconcileResult(newly_owned=len(to_own))
