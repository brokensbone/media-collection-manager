from .ports.transmission import TorrentUploader


class TorrentSubmissionService:
    """Starts downloads from uploaded torrent metainfo without retaining the file."""

    def __init__(self, *, uploader: TorrentUploader, api_configured: bool) -> None:
        self._uploader = uploader
        self._api_configured = api_configured

    def submit(self, metainfo: bytes) -> None:
        if not self._api_configured:
            raise RuntimeError("Transmission RPC is not configured.")
        self._uploader.add_torrent(metainfo)
