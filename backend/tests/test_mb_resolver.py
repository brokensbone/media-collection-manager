import urllib.parse

import httpx
import respx

from mcm.adapters.mb_resolver import HttpxMusicBrainzResolver

MB = "https://mb.test/ws/2"


def _resolver() -> HttpxMusicBrainzResolver:
    return HttpxMusicBrainzResolver(
        base_url=MB, user_agent="ua", min_interval=0.0, text_min_score=90
    )


@respx.mock
def test_barcode_tier_wins() -> None:
    respx.get(f"{MB}/release").mock(
        return_value=httpx.Response(200, json={"releases": [{"release-group": {"id": "rg-bar"}}]})
    )
    assert _resolver().resolve(upc="111", isrcs=["i1"], artist="A", title="T") == "rg-bar"


@respx.mock
def test_text_tier_beats_isrc_when_confident() -> None:
    # No barcode: text is tried before the ISRC cluster, so a confident text hit wins outright
    # and the per-track ISRC lookups never run.
    text = respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 95}]})
    )
    isrc = respx.get(f"{MB}/recording").mock(
        return_value=httpx.Response(
            200, json={"recordings": [{"releases": [{"release-group": {"id": "rg-isrc"}}]}]}
        )
    )
    assert _resolver().resolve(upc=None, isrcs=["i1", "i2"], artist="A", title="T") == "rg-text"
    assert text.called and not isrc.called


@respx.mock
def test_isrc_tier_is_the_fallback_when_text_misses() -> None:
    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 50}]})
    )
    respx.get(f"{MB}/recording").mock(
        return_value=httpx.Response(
            200, json={"recordings": [{"releases": [{"release-group": {"id": "rg-isrc"}}]}]}
        )
    )
    assert _resolver().resolve(upc=None, isrcs=["i1", "i2"], artist="A", title="T") == "rg-isrc"


@respx.mock
def test_text_tier_accepts_high_score() -> None:
    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 95}]})
    )
    assert _resolver().resolve(upc=None, isrcs=[], artist="A", title="T") == "rg-text"


@respx.mock
def test_text_query_uses_sanitised_terms_not_a_quoted_phrase() -> None:
    # A title's punctuation ("Nothing/Everything") is dropped to bare, field-scoped terms so it
    # matches MB's differently-spaced "Nothing / Everything" — a quoted phrase misses that.
    route = respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg", "score": 100}]})
    )
    got = _resolver().resolve(
        upc=None, isrcs=[], artist="The Lovely Eggs", title="Nothing/Everything"
    )
    assert got == "rg"
    sent = urllib.parse.unquote_plus(str(route.calls[0].request.url))
    assert "releasegroup:(Nothing Everything)" in sent
    assert '"Nothing/Everything"' not in sent  # not a rigid quoted phrase


@respx.mock
def test_low_score_text_and_no_isrcs_is_unresolved() -> None:
    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 50}]})
    )
    assert _resolver().resolve(upc=None, isrcs=[], artist="A", title="T") is None


@respx.mock
def test_503_is_retried_with_backoff() -> None:
    # MB's rate-limit signal: the resolver backs off and retries rather than abandoning the album.
    route = respx.get(f"{MB}/release-group").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 95}]}),
        ]
    )
    assert _resolver().resolve(upc=None, isrcs=[], artist="A", title="T") == "rg-text"
    assert route.call_count == 3


@respx.mock
def test_persistent_503_gives_up_after_retries() -> None:
    route = respx.get(f"{MB}/release-group").mock(return_value=httpx.Response(503))
    resolver = HttpxMusicBrainzResolver(
        base_url=MB, user_agent="ua", min_interval=0.0, text_min_score=90, max_retries=2
    )
    try:
        resolver.resolve(upc=None, isrcs=[], artist="A", title="T")
        raise AssertionError("expected the persistent 503 to surface")
    except httpx.HTTPStatusError:
        pass
    assert route.call_count == 3  # initial try + 2 retries
