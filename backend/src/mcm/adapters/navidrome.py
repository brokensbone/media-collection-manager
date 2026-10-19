"""OpenSubsonic playlist adapter. Match files exactly; never guess by title."""

import hashlib
import secrets
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlencode

import httpx

from ..config import Settings


class NavidromeError(Exception):
    pass


def relative_path(value: str, prefix: str = "") -> str | None:
    """Only strip an explicitly configured path root, on a directory boundary."""
    path = PurePosixPath(value)
    if not value or ".." in path.parts:
        return None
    if prefix:
        try:
            path = path.relative_to(PurePosixPath(prefix))
        except ValueError:
            return None
    if path.is_absolute() or not path.parts:
        return None
    return str(path)


class NavidromeClient:
    def __init__(self, settings: Settings, client: httpx.Client) -> None:
        self.settings = settings
        self.client = client

    def call(self, endpoint: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        auth = [("v", "1.16.1"), ("c", "MCM"), ("f", "json")]
        if self.settings.navidrome_api_key:
            auth.append(("apiKey", self.settings.navidrome_api_key))
        elif self.settings.navidrome_username and self.settings.navidrome_password:
            salt = secrets.token_hex(16)
            token = hashlib.md5(
                (self.settings.navidrome_password + salt).encode(), usedforsecurity=False
            ).hexdigest()
            auth.extend([("u", self.settings.navidrome_username), ("t", token), ("s", salt)])
        else:
            raise NavidromeError("Navidrome credentials are not configured")
        try:
            # Form POST keeps credentials and long song lists out of URLs and access logs.
            response = self.client.post(
                self.settings.navidrome_url.rstrip("/") + "/rest/" + endpoint,
                content=urlencode(auth + params).encode(),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "MCM/1",
                },
            )
            response.raise_for_status()
            body = response.json()["subsonic-response"]
            if not isinstance(body, dict):
                raise ValueError
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Never include request URLs, server messages or secrets in persisted errors.
            raise NavidromeError(f"Navidrome {endpoint} request failed") from exc
        if body.get("status") != "ok":
            code = body.get("error", {}).get("code", "unknown")
            raise NavidromeError(f"Navidrome {endpoint} rejected the request (code {code})")
        return body

    def song_index(self) -> dict[str, set[str]]:
        prefix = self.settings.navidrome_path_prefix or self.settings.music_dir
        if not prefix:
            raise NavidromeError("Set MCM_NAVIDROME_PATH_PREFIX to Navidrome's music root")
        index: dict[str, set[str]] = {}
        offset = 0
        seen_ids: set[str] = set()
        while True:
            params = [
                ("query", ""),
                ("artistCount", "0"),
                ("albumCount", "0"),
                ("songCount", "500"),
                ("songOffset", str(offset)),
            ]
            if self.settings.navidrome_music_folder_id:
                params.append(("musicFolderId", self.settings.navidrome_music_folder_id))
            songs = self.call("search3", params).get("searchResult3", {}).get("song", [])
            if not songs:
                return index
            page_ids = {str(song["id"]) for song in songs}
            if page_ids <= seen_ids:
                raise NavidromeError("Navidrome catalogue pagination did not advance")
            seen_ids.update(page_ids)
            for song in songs:
                reported = song.get("path", "")
                if not PurePosixPath(reported).is_absolute():
                    raise NavidromeError(
                        "Enable Report Real Path for the MCM player in Navidrome Settings > Players"
                    )
                path = relative_path(reported, prefix)
                if path and song.get("id"):
                    index.setdefault(path, set()).add(str(song["id"]))
            offset += len(songs)

    def replace_playlist(self, name: str, playlist_id: str | None, songs: list[str]) -> str:
        if playlist_id is None:
            # Recover after a lost create response or local commit failure. Reserve these
            # names for MCM in a dedicated account; multiple matches require intervention.
            playlists = self.call("getPlaylists", []).get("playlists", {}).get("playlist", [])
            matches = [p for p in playlists if p.get("name") == name]
            if len(matches) > 1:
                raise NavidromeError("Multiple Navidrome playlists have the reserved MCM name")
            if matches:
                playlist_id = str(matches[0]["id"])
        params = [("playlistId", playlist_id)] if playlist_id else [("name", name)]
        params.extend(("songId", song) for song in songs)
        result = self.call("createPlaylist", params).get("playlist", {})
        if not result.get("id"):
            raise NavidromeError("Navidrome did not return a playlist ID")
        return str(result["id"])

    def verify_playlist(self, playlist_id: str, songs: list[str]) -> None:
        playlist = self.call("getPlaylist", [("id", playlist_id)]).get("playlist", {})
        if [str(entry["id"]) for entry in playlist.get("entry", [])] != songs:
            raise NavidromeError("Navidrome playlist read-back did not match programme order")
