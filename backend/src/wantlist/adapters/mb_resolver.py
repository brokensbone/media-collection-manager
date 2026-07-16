import time
import urllib.parse
from collections import Counter
from typing import Any

import httpx


class HttpxMusicBrainzResolver:
    """3-tier Spotify→release-group resolution (barcode → ISRC cluster → fuzzy text), the
    D0 spike logic productionised. Base URL + User-Agent + rate limit are injected (§5/§14)."""

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        min_interval: float,
        text_min_score: int,
        isrc_cap: int = 8,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30)
        self._min_interval = min_interval
        self._text_min_score = text_min_score
        self._isrc_cap = isrc_cap
        self._last = 0.0

    def resolve(self, *, upc: str | None, isrcs: list[str], artist: str, title: str) -> str | None:
        if upc:
            rgids = self._by_barcode(upc)
            if rgids:
                return Counter(rgids).most_common(1)[0][0]
        if isrcs:
            tally: Counter[str] = Counter()
            for isrc in isrcs[: self._isrc_cap]:
                tally.update(self._by_isrc(isrc))
            if tally:
                return tally.most_common(1)[0][0]
        return self._by_text(artist, title)

    def _by_barcode(self, upc: str) -> list[str]:
        data = self._get("release", f"barcode:{upc}")
        return [
            r["release-group"]["id"] for r in data.get("releases", []) if r.get("release-group")
        ]

    def _by_isrc(self, isrc: str) -> list[str]:
        data = self._get("recording", f"isrc:{isrc}")
        return [
            rel["release-group"]["id"]
            for rec in data.get("recordings", [])
            for rel in rec.get("releases", [])
            if rel.get("release-group")
        ]

    def _by_text(self, artist: str, title: str) -> str | None:
        query = f'artist:"{_esc(artist)}" AND releasegroup:"{_esc(title)}"'
        groups = self._get("release-group", query).get("release-groups", [])
        if groups and int(groups[0].get("score", 0)) >= self._text_min_score:
            return str(groups[0]["id"])
        return None

    def _get(self, path: str, query: str) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 25})
        resp = self._client.get(f"{self._base_url}/{path}?{params}")
        self._last = time.monotonic()
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def _esc(text: str) -> str:
    return text.replace('"', " ").replace(":", " ")
