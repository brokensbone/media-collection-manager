import base64
from typing import Any

import httpx

from ..ports.transmission import AddedTorrent, Torrent

_SESSION_HEADER = "X-Transmission-Session-Id"
_FIELDS = ["hashString", "name", "downloadDir", "percentDone", "files"]


class HttpxTransmissionClient:
    """Transmission RPC over httpx, handling the 409 session-id handshake (SPEC §12)."""

    def __init__(self, rpc_url: str, user: str, password: str) -> None:
        self._url = rpc_url
        self._auth = (user, password) if user else None
        self._session_id = ""

    def ping(self) -> None:
        """Lightweight liveness check for the Transmission page's connection test — does the
        session-id handshake and a session-get. Raises on any failure (auth, network, 409)."""
        self._rpc({"method": "session-get", "arguments": {"fields": ["version"]}})

    def completed_torrents(self) -> list[Torrent]:
        data = self._rpc({"method": "torrent-get", "arguments": {"fields": _FIELDS}})
        torrents = data.get("arguments", {}).get("torrents", [])
        return [
            Torrent(
                hash=t["hashString"],
                name=t["name"],
                download_dir=t["downloadDir"],
                files=[f["name"] for f in t.get("files", [])],
            )
            for t in torrents
            if t.get("percentDone") == 1
        ]

    def add_torrent(self, metainfo: bytes) -> AddedTorrent:
        """Hand a .torrent file to Transmission without retaining a local copy.

        Transmission answers `success` either way and says which happened in the shape of
        the payload: `torrent-added` for a new download, `torrent-duplicate` for one it
        already had. Both spellings are accepted because the RPC documentation writes these
        keys with underscores while the wire uses hyphens."""
        data = self._rpc(
            {
                "method": "torrent-add",
                "arguments": {"metainfo": base64.b64encode(metainfo).decode("ascii")},
            }
        )
        args = data.get("arguments", {})
        for key in ("torrent-duplicate", "torrent_duplicate"):
            if key in args:
                return _added(args[key], already_present=True)
        for key in ("torrent-added", "torrent_added"):
            if key in args:
                return _added(args[key], already_present=False)
        # An older or unusual Transmission that says only "success": treat it as added
        # rather than inventing a duplicate, since that is what it has always meant.
        return AddedTorrent(name="", hash="", already_present=False)

    def _rpc(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(2):
            headers = {_SESSION_HEADER: self._session_id} if self._session_id else {}
            resp = httpx.post(self._url, json=body, headers=headers, auth=self._auth, timeout=30)
            if resp.status_code == 409 and attempt == 0:
                self._session_id = resp.headers.get(_SESSION_HEADER, "")
                continue  # retry once with the fresh session id
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        raise RuntimeError("Transmission session-id handshake failed")


def _added(payload: dict[str, Any], *, already_present: bool) -> AddedTorrent:
    return AddedTorrent(
        name=str(payload.get("name", "")),
        hash=str(payload.get("hashString") or payload.get("hash_string") or ""),
        already_present=already_present,
    )
