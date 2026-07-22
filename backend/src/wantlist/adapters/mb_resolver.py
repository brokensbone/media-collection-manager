import time
import urllib.parse
from collections import Counter
from typing import Any

import httpx


class HttpxMusicBrainzResolver:
    """Spotify→release-group resolution (§5/§14), tiers ordered cheapest-and-most-direct first:

    1. barcode (`release?barcode=`) — exact when the UPC is in MB, one call.
    2. artist+title text (`release-group?query=`) — one call that returns the release-group
       *directly* and is both artist-scoped and score-gated.
    3. ISRC cluster (`recording?isrc=`) — fallback only; up to `isrc_cap` lookups (one per track).

    Text sits ahead of the ISRC cluster because we only ever need release-group granularity: one
    artist-scoped text search resolves it, whereas the ISRC cluster fires a lookup per track and
    then reads the release-group off the release anyway. ISRC stays as the fallback for albums the
    text search can't place confidently. MB 503s (its rate-limit/busy signal) are retried with
    backoff so a transient throttle doesn't abandon an album for the whole pass. This is the D0
    spike logic productionised; base URL + User-Agent + rate limit are injected (§5/§14)."""

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        min_interval: float,
        text_min_score: int,
        isrc_cap: int = 3,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30)
        self._min_interval = min_interval
        self._text_min_score = text_min_score
        self._isrc_cap = isrc_cap
        self._max_retries = max_retries
        self._last = 0.0

    def resolve(self, *, upc: str | None, isrcs: list[str], artist: str, title: str) -> str | None:
        if upc:
            rgids = self._by_barcode(upc)
            if rgids:
                return Counter(rgids).most_common(1)[0][0]
        text_rgid = self._by_text(artist, title)
        if text_rgid:
            return text_rgid
        if isrcs:
            tally: Counter[str] = Counter()
            for isrc in isrcs[: self._isrc_cap]:
                tally.update(self._by_isrc(isrc))
            if tally:
                return tally.most_common(1)[0][0]
        return None

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
        params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 25})
        url = f"{self._base_url}/{path}?{params}"
        for attempt in range(self._max_retries + 1):
            elapsed = time.monotonic() - self._last
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            resp = self._client.get(url)
            self._last = time.monotonic()
            if resp.status_code == 503 and attempt < self._max_retries:
                time.sleep(self._retry_delay(resp, attempt))
                continue
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        raise RuntimeError("unreachable: the retry loop always returns or raises")

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        """Seconds to wait before retrying a 503: MB's Retry-After when it sends one, else an
        exponential backoff off the base interval. Capped so a bogus header can't stall a pass."""
        backoff: float = self._min_interval * 2**attempt
        header = resp.headers.get("Retry-After")
        if header:
            try:
                backoff = max(backoff, float(header))
            except ValueError:
                pass  # HTTP-date form — ignore and use the computed backoff
        return min(backoff, 30.0)


def _esc(text: str) -> str:
    return text.replace('"', " ").replace(":", " ")
