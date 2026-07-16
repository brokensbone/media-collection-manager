import urllib.parse


def bandcamp_search_url(artist: str, title: str) -> str:
    """A deterministic Bandcamp search URL — one-click buy-assist (SPEC §7). No API, no
    scraping; the search page always resolves."""
    query = urllib.parse.urlencode({"q": f"{artist} {title}"})
    return f"https://bandcamp.com/search?{query}"
