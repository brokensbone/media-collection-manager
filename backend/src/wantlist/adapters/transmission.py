import base64
from typing import Any

import httpx

from ..ports.transmission import Torrent

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

    def add_torrent(self, metainfo: bytes) -> None:
        """Hand a .torrent file to Transmission without retaining a local copy."""
        self._rpc(
            {
                "method": "torrent-add",
                "arguments": {"metainfo": base64.b64encode(metainfo).decode("ascii")},
            }
        )

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
