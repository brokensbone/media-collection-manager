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


@dataclass
class AddedTorrent:
    """What Transmission did with a submitted .torrent.

    `already_present` separates the two outcomes Transmission reports as success: a new
    download started, and a torrent it was already carrying. Both are fine, but only one
    of them means anything started."""

    name: str
    hash: str
    already_present: bool


class TorrentUploader(Protocol):
    """The small RPC surface needed to start a download from a .torrent file."""

    def add_torrent(self, metainfo: bytes) -> AddedTorrent: ...
