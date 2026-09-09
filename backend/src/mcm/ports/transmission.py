from dataclasses import dataclass
from typing import Protocol


@dataclass
class Torrent:
    hash: str
    name: str
    download_dir: str
    files: list[str]  # paths relative to download_dir


class TransmissionClient(Protocol):
    """The Transmission RPC surface we depend on (SPEC §12). Base URL is injected."""

    def completed_torrents(self) -> list[Torrent]: ...


class TorrentUploader(Protocol):
    """The small RPC surface needed to start a download from a .torrent file."""

    def add_torrent(self, metainfo: bytes) -> None: ...
