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


# --- judgement-based text tier (§5) -------------------------------------------

ALVA = {
    "id": "rg-alva",
    "score": 100,
    "title": "12 Conversations",
    "artist-credit": [{"artist": {"name": "Alva Noto"}}, {"artist": {"name": "坂本龍一"}}],
    "first-release-date": "2018-02-23",
    "primary-type": "Album",
}
WRONG = {
    "id": "rg-wrong",
    "score": 100,
    "title": "New Irish Hymns #2",
    "artist-credit": [{"artist": {"name": "Margaret Becker"}}],
}


class RecordingJudge:
    """Answers with whatever it was told to, and keeps what it was asked."""

    def __init__(self, judgement: object | None) -> None:
        self.judgement = judgement
        self.asked: list[object] = []
        self.artist = self.title = ""

    def choose(self, *, artist: str, title: str, candidates: list[object]) -> object | None:
        self.artist, self.title, self.asked = artist, title, candidates
        return self.judgement


def _judged(judge: object, min_probability: float = 0.6) -> HttpxMusicBrainzResolver:
    return HttpxMusicBrainzResolver(
        base_url=MB,
        user_agent="ua",
        min_interval=0.0,
        text_min_score=90,
        judge=judge,
        min_probability=min_probability,
    )


@respx.mock
def test_search_widens_to_the_leading_artist() -> None:
    # Spotify's comma-joined credit is not a MusicBrainz artist, so quoting the whole of it
    # asks for a credit that does not exist there. Only the leading name is searchable.
    from mcm.ports.release_group_judge import ReleaseGroupJudgement

    route = respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [ALVA]})
    )
    judge = RecordingJudge(None)
    judge.judgement = ReleaseGroupJudgement(None, 1.0, 1.0)
    _judged(judge).resolve(
        upc=None, isrcs=[], artist="Alva Noto, Ryuichi Sakamoto", title="12 Conversations"
    )
    query = urllib.parse.parse_qs(route.calls[0].request.url.query.decode())["query"][0]
    assert 'artist:"Alva Noto"' in query
    assert "Ryuichi Sakamoto" not in query


@respx.mock
def test_the_judgement_decides_not_the_score() -> None:
    # MusicBrainz scores this 100 and it is a different artist's album entirely.
    from mcm.ports.release_group_judge import ReleaseGroupJudgement

    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [WRONG]})
    )
    respx.get(f"{MB}/recording").mock(return_value=httpx.Response(200, json={"recordings": []}))
    judge = RecordingJudge(ReleaseGroupJudgement(None, 0.97, 0.97))
    assert (
        _judged(judge).resolve(upc=None, isrcs=[], artist="Becker & Mukai", title="Spirit Only")
        is None
    )


@respx.mock
def test_a_chosen_candidate_resolves() -> None:
    from mcm.ports.release_group_judge import ReleaseGroupCandidate, ReleaseGroupJudgement

    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [ALVA]})
    )
    judge = RecordingJudge(
        ReleaseGroupJudgement(
            ReleaseGroupCandidate(
                id="rg-alva", artist="Alva Noto, 坂本龍一", title="12 Conversations"
            ),
            0.95,
            0.72,
        )
    )
    got = _judged(judge).resolve(
        upc=None, isrcs=[], artist="Alva Noto, Ryuichi Sakamoto", title="12 Conversations"
    )
    assert got == "rg-alva"


@respx.mock
def test_the_judge_sees_the_full_spotify_credit_and_musicbrainz_own() -> None:
    from mcm.ports.release_group_judge import ReleaseGroupJudgement

    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [ALVA]})
    )
    judge = RecordingJudge(ReleaseGroupJudgement(None, 1.0, 1.0))
    _judged(judge).resolve(
        upc=None, isrcs=[], artist="Alva Noto, Ryuichi Sakamoto", title="12 Conversations"
    )
    # Narrowing the *search* must not narrow what the judgement is told.
    assert judge.artist == "Alva Noto, Ryuichi Sakamoto"
    assert judge.asked[0].artist == "Alva Noto, 坂本龍一"
    assert judge.asked[0].first_release_date == "2018-02-23"


@respx.mock
def test_a_weak_probability_leaves_the_album_unresolved() -> None:
    from mcm.ports.release_group_judge import ReleaseGroupCandidate, ReleaseGroupJudgement

    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [ALVA]})
    )
    respx.get(f"{MB}/recording").mock(return_value=httpx.Response(200, json={"recordings": []}))
    judge = RecordingJudge(
        ReleaseGroupJudgement(ReleaseGroupCandidate(id="rg-alva", artist="a", title="t"), 0.4, 0.4)
    )
    assert _judged(judge).resolve(upc=None, isrcs=[], artist="A", title="T") is None


@respx.mock
def test_an_unavailable_judge_falls_back_to_the_score_gate() -> None:
    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [{"id": "rg-text", "score": 95}]})
    )
    assert (
        _judged(RecordingJudge(None)).resolve(upc=None, isrcs=[], artist="A", title="T")
        == "rg-text"
    )


@respx.mock
def test_the_barcode_tier_never_consults_the_judge() -> None:
    # An exact barcode needs no judgement, and paying for one would be waste.
    respx.get(f"{MB}/release").mock(
        return_value=httpx.Response(200, json={"releases": [{"release-group": {"id": "rg-bar"}}]})
    )
    judge = RecordingJudge(None)
    assert _judged(judge).resolve(upc="111", isrcs=[], artist="A", title="T") == "rg-bar"
    assert judge.asked == []


@respx.mock
def test_a_clear_answer_is_taken_even_when_the_distribution_is_not_concentrated() -> None:
    # A short candidate list splits 0.76/0.24 on an exact artist-and-title match: a clear
    # answer, and an unconcentrated distribution. Gating on confidence would discard it.
    from mcm.ports.release_group_judge import ReleaseGroupCandidate, ReleaseGroupJudgement

    respx.get(f"{MB}/release-group").mock(
        return_value=httpx.Response(200, json={"release-groups": [ALVA]})
    )
    judge = RecordingJudge(
        ReleaseGroupJudgement(
            ReleaseGroupCandidate(id="rg-alva", artist="a", title="t"),
            0.76,
            0.52,
        )
    )
    assert _judged(judge).resolve(upc=None, isrcs=[], artist="A", title="T") == "rg-alva"
