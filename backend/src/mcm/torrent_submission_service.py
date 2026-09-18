from .adapters.event_log import NullEventSink
from .ports.events import EventSink
from .ports.transmission import AddedTorrent, TorrentUploader


class TorrentSubmissionService:
    """Starts downloads from uploaded torrent metainfo without retaining the file."""

    def __init__(
        self,
        *,
        uploader: TorrentUploader,
        api_configured: bool,
        events: EventSink | None = None,
    ) -> None:
        self._uploader = uploader
        self._api_configured = api_configured
        self._events = events or NullEventSink()

    def submit(self, metainfo: bytes) -> AddedTorrent:
        if not self._api_configured:
            raise RuntimeError("Transmission RPC is not configured.")
        added = self._uploader.add_torrent(metainfo)
        label = added.name or added.hash or "a torrent"
        if added.already_present:
            self._events.emit(
                job="transmission",
                type="duplicate",
                message=f"Already downloading, nothing started: '{label}'",
            )
        else:
            self._events.emit(
                job="transmission",
                type="added",
                message=f"Started downloading '{label}'",
            )
        return added
