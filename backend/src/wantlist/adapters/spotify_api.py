from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

import httpx

from ..ports.spotify_api import SavedAlbum


class HttpxSpotifyApiClient:
    """Reads the Spotify Web API over httpx. Base URL injected so E2E can stub it (§14)."""

    def __init__(self, api_url: str, art_target_px: int) -> None:
        self._api_url = api_url.rstrip("/")
        self._art_target_px = art_target_px

    def saved_albums(self, access_token: str) -> Iterable[SavedAlbum]:
        headers = {"Authorization": f"Bearer {access_token}"}
        url: str | None = f"{self._api_url}/me/albums?limit=50"
        while url:
            resp = httpx.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            page = resp.json()
            yield from self._parse_page(page)
            url = page.get("next")

    def album_isrcs(self, access_token: str, album_id: str) -> list[str]:
        """Fetch an album's track ISRCs (Tier-2 resolution input, §5). ISRCs live on the
        full track objects, not the album's simplified tracks — so a second /tracks call."""
        headers = {"Authorization": f"Bearer {access_token}"}
        album = self._get_json(f"{self._api_url}/albums/{album_id}", headers)
        track_ids = [t["id"] for t in album.get("tracks", {}).get("items", []) if t.get("id")]
        isrcs: list[str] = []
        for start in range(0, len(track_ids), 50):
            batch = ",".join(track_ids[start : start + 50])
            data = self._get_json(f"{self._api_url}/tracks?ids={batch}", headers)
            for track in data.get("tracks", []):
                isrc = (track or {}).get("external_ids", {}).get("isrc")
                if isrc:
                    isrcs.append(isrc)
        return isrcs

    @staticmethod
    def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _parse_page(self, page: dict[str, Any]) -> Iterator[SavedAlbum]:
        for item in page["items"]:
            album = item["album"]
            yield SavedAlbum(
                spotify_id=album["id"],
                artist=", ".join(a["name"] for a in album["artists"]),
                title=album["name"],
                upc=album.get("external_ids", {}).get("upc"),
                added_at=_parse_dt(item.get("added_at")),
                art_url=self._best_image(album.get("images", [])),
            )

    def _best_image(self, images: list[dict[str, Any]]) -> str | None:
        sized = [i for i in images if i.get("url") and i.get("width")]
        if not sized:
            return images[0]["url"] if images else None
        best = min(sized, key=lambda i: abs(int(i["width"]) - self._art_target_px))
        return str(best["url"])


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
