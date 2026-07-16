import httpx


def fetch_image(url: str) -> tuple[str, bytes]:
    """Download cover art bytes (SPEC §4b). Injected into IngestService so tests can fake it."""
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "image/jpeg")
    return content_type, resp.content
