import httpx
import respx

from wantlist.adapters.mb_resolver import HttpxMusicBrainzResolver

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
def test_isrc_tier_when_no_barcode() -> None:
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
def test_text_tier_rejects_low_score() -> None:
    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 50}]})
    )
    assert _resolver().resolve(upc=None, isrcs=[], artist="A", title="T") is None
