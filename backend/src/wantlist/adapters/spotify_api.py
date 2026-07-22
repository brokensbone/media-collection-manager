import urllib.parse
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

import httpx

from ..ports.spotify_api import Play, SavedAlbum


class HttpxSpotifyApiClient:
    """Reads the Spotify Web API over httpx. Base URL injected so E2E can stub it (§14)."""

    def __init__(self, api_url: str, art_target_px: int, market: str = "GB") -> None:
        self._api_url = api_url.rstrip("/")
        self._art_target_px = art_target_px
        self._market = market

    def saved_albums(self, access_token: str) -> Iterable[SavedAlbum]:
        headers = {"Authorization": f"Bearer {access_token}"}
        url: str | None = f"{self._api_url}/me/albums?limit=50"
        while url:
            resp = httpx.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            page = resp.json()
            yield from self._parse_page(page)
            url = page.get("next")

    def search_album(self, access_token: str, query: str) -> SavedAlbum | None:
        """Find an album by free text (D21 reverse-match): enrich a directly-imported album
        with its Spotify id + cover art. Returns the top hit, or None if nothing matches."""
        headers = {"Authorization": f"Bearer {access_token}"}
        q = urllib.parse.quote(query)
        data = self._get_json(f"{self._api_url}/search?type=album&limit=1&q={q}", headers)
        items = data.get("albums", {}).get("items", [])
        return self._to_saved(items[0], added_at=None) if items else None

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

    def followed_artist_ids(self, access_token: str) -> list[str]:
        headers = {"Authorization": f"Bearer {access_token}"}
        url: str | None = f"{self._api_url}/me/following?type=artist&limit=50"
        ids: list[str] = []
        while url:
            page = self._get_json(url, headers).get("artists", {})
            ids.extend(a["id"] for a in page.get("items", []) if a.get("id"))
            url = page.get("next")
        return ids

    def artist_albums(self, access_token: str, artist_id: str) -> list[SavedAlbum]:
        headers = {"Authorization": f"Bearer {access_token}"}
        # market dedupes Spotify's per-country album variants (else the same release returns
        # different ids over time and an old album resurfaces as a bogus "new release"), and
        # restricts to albums actually playable in that market (§6b).
        url: str | None = (
            f"{self._api_url}/artists/{artist_id}/albums"
            f"?include_groups=album&limit=50&market={self._market}"
        )
        albums: list[SavedAlbum] = []
        while url:
            page = self._get_json(url, headers)
            albums.extend(self._to_saved(a, added_at=None) for a in page.get("items", []))
            url = page.get("next")
        return albums

    def save_album(self, access_token: str, spotify_album_id: str) -> None:
        resp = httpx.put(
            f"{self._api_url}/me/albums",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"ids": spotify_album_id},
            timeout=30,
        )
        resp.raise_for_status()

    def recently_played(self, access_token: str) -> list[Play]:
        """The last ~50 plays (SPEC §4a). No deep history exists; we accumulate over time."""
        headers = {"Authorization": f"Bearer {access_token}"}
        data = self._get_json(f"{self._api_url}/me/player/recently-played?limit=50", headers)
        plays: list[Play] = []
        for item in data.get("items", []):
            track = item.get("track") or {}
            if not track.get("id") or not item.get("played_at"):
                continue
            plays.append(
                Play(
                    spotify_track_id=track["id"],
                    spotify_album_id=(track.get("album") or {}).get("id"),
                    played_at=datetime.fromisoformat(item["played_at"]),
                )
            )
        return plays

    @staticmethod
    def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _parse_page(self, page: dict[str, Any]) -> Iterator[SavedAlbum]:
        for item in page["items"]:
            yield self._to_saved(item["album"], added_at=_parse_dt(item.get("added_at")))

    def _to_saved(self, album: dict[str, Any], added_at: datetime | None) -> SavedAlbum:
        artists = album.get("artists", [])
        return SavedAlbum(
            spotify_id=album["id"],
            artist=", ".join(a["name"] for a in artists),
            artist_id=artists[0]["id"] if artists and artists[0].get("id") else None,
            title=album["name"],
            upc=album.get("external_ids", {}).get("upc"),
            added_at=added_at,
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
