import re
import time
import urllib.parse
from collections import Counter
from typing import Any

import httpx

from ..ports.release_group_judge import ReleaseGroupCandidate, ReleaseGroupJudge


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
        judge: ReleaseGroupJudge | None = None,
        min_probability: float = 0.6,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30)
        self._min_interval = min_interval
        self._text_min_score = text_min_score
        self._isrc_cap = isrc_cap
        self._max_retries = max_retries
        self._judge = judge
        self._min_probability = min_probability
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
        return (
            self._by_text_judged(artist, title)
            if self._judge
            else self._by_text_scored(artist, title)
        )

    def _by_text_scored(self, artist: str, title: str) -> str | None:
        # Field-scoped bare terms for the title, not a quoted phrase: Spotify and MusicBrainz
        # punctuate/space titles differently ("Nothing/Everything" vs "Nothing / Everything"),
        # and an exact phrase misses across that. The artist stays a quoted phrase (loosening it
        # balloons the match set), and the score gate guards against loose over-matching.
        terms = _terms(title)
        if not terms:
            return None
        query = f'artist:"{_esc(artist)}" AND releasegroup:({terms})'
        groups = self._get("release-group", query).get("release-groups", [])
        if groups and int(groups[0].get("score", 0)) >= self._text_min_score:
            return str(groups[0]["id"])
        return None

    def _by_text_judged(self, artist: str, title: str) -> str | None:
        """Search on the leading artist alone and let a judgement pick from what comes back.

        Spotify joins every credited artist with commas, so quoting the whole string asks
        MusicBrainz for a single credit that does not exist there: "Alva Noto, Ryuichi
        Sakamoto" finds nothing, though the album is present, credited "Alva Noto, 坂本龍一".
        Searching the first artist alone finds it — and also finds unrelated records the
        score cannot separate, reaching 100 on a different artist's album entirely. So the
        looser search and the judgement are a pair: neither is safe on its own.
        """
        terms = _terms(title)
        if not terms:
            return None
        lead = _lead_artist(artist)
        if not lead:
            return None
        query = f'artist:"{_esc(lead)}" AND releasegroup:({terms})'
        groups = self._get("release-group", query).get("release-groups", [])
        candidates = [
            ReleaseGroupCandidate(
                id=str(g["id"]),
                artist=_credit(g),
                title=str(g.get("title", "")),
                first_release_date=g.get("first-release-date") or None,
                primary_type=g.get("primary-type") or None,
            )
            for g in groups
        ]
        assert self._judge is not None
        judgement = self._judge.choose(artist=artist, title=title, candidates=candidates)
        if judgement is None:  # judge unavailable — fall back rather than lose the album
            return self._by_text_scored(artist, title)
        # Gate on the probability of the answer, not on confidence. Confidence measures
        # how concentrated the distribution is, and these candidate lists are short — often a
        # single release group against "none of these". An exact artist-and-title match splits
        # 0.76/0.24 there, which is a clear answer and an unconcentrated distribution at once.
        if judgement.candidate is None or judgement.probability < self._min_probability:
            return None
        return judgement.candidate.id

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


_SPECIAL = re.compile(r"[^\w\s]", re.UNICODE)


def _terms(text: str) -> str:
    """Bare, space-separated search terms: drop Lucene punctuation (`/`, `!`, `?`, …) so a
    field query matches across Spotify↔MusicBrainz punctuation and spacing differences."""
    return " ".join(_SPECIAL.sub(" ", text).split())


def _lead_artist(artist: str) -> str:
    """The first credited artist. Spotify joins collaborators with commas; MusicBrainz
    holds one credit, so only the leading name is reliably searchable."""
    return artist.split(",")[0].strip()


def _credit(group: dict[str, Any]) -> str:
    """MusicBrainz's own artist credit for a release group, as it would be displayed."""
    names = [c["artist"]["name"] for c in group.get("artist-credit", []) if c.get("artist")]
    return ", ".join(names)
