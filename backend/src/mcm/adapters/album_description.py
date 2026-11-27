"""Best-effort Bandcamp discovery. Only exact artist/title matches become evidence."""

import html
import json
import re
import unicodedata
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


class BandcampPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.about = ""
        self.tags: list[str] = []
        self.links: list[str] = []
        self._tag = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta" and a.get("property") == "og:title":
            self.title = a.get("content") or ""
        if a.get("data-tralbum"):
            data = json.loads(a["data-tralbum"] or "{}")
            self.about = str((data.get("current") or {}).get("about") or "")
        if tag == "a":
            if a.get("href"):
                self.links.append(a["href"] or "")
            self._tag = "tag" in (a.get("class") or "").split()

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._tag = False

    def handle_data(self, data: str) -> None:
        if self._tag and data.strip():
            self.tags.append(data.strip())


def album_url(value: str) -> str | None:
    u = urlsplit(value)
    host = u.hostname or ""
    if (
        u.scheme == "https"
        and host.endswith(".bandcamp.com")
        and not u.username
        and not u.password
        and u.port in (None, 443)
        and re.fullmatch(r"/album/[a-zA-Z0-9-]+", u.path)
    ):
        return urlunsplit(("https", host, u.path, "", ""))
    return None


class BandcampDescriptions:
    def lookup(self, album: dict[str, Any]) -> dict[str, Any]:
        evidence: dict[str, Any] = {"sources": [], "retrieved_at": datetime.now(UTC).isoformat()}
        unavailable = False
        with httpx.Client(timeout=4, follow_redirects=False) as client:
            # Search is best-effort: Bandcamp can return an interstitial rather than results.
            urls = []
            try:
                search = client.get(
                    "https://bandcamp.com/search",
                    params={
                        "q": f"{album['artist']} {album['title']}",
                        "item_type": "a",
                    },
                )
                search.raise_for_status()
                page = BandcampPage()
                page.feed(search.text[:2_000_000])
                urls = list(dict.fromkeys(u for link in page.links if (u := album_url(link))))
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                unavailable = True
            # Try the conventional artist URL if discovery did not find a candidate.
            # It is only a candidate: exact title AND artist must match the returned page.
            if not urls:
                artist = normalized(album["artist"])
                title = re.sub(
                    r"[^a-z0-9]+",
                    "-",
                    unicodedata.normalize("NFKD", album["title"])
                    .encode("ascii", "ignore")
                    .decode()
                    .lower(),
                ).strip("-")
                candidate = album_url(f"https://{artist}.bandcamp.com/album/{title}")
                if candidate:
                    urls.append(candidate)
            for url in urls[:3]:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    release = BandcampPage()
                    release.feed(response.text[:2_000_000])
                    expected = f"{album['title']}, by {album['artist']}"
                    if normalized(release.title) != normalized(expected):
                        continue
                    text = html.unescape(re.sub(r"<[^>]+>", " ", release.about)).strip()
                    if text or release.tags:
                        evidence["sources"] = [
                            {
                                "url": url,
                                "provider": "Bandcamp",
                                "description": text[:1800],
                                "tags": release.tags[:20],
                            }
                        ]
                        break
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    unavailable = True
        if not evidence["sources"]:
            evidence["notice"] = (
                "Album description lookup unavailable; using catalogue context."
                if unavailable
                else "No exact album description found; using catalogue context."
            )
        return evidence
