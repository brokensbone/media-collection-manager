"""Retrieval breadth, and the policy around a judgement (SPEC §12)."""

from mcm.adapters.typesafe_judge import NONE, TypeSafeAlbumJudge
from mcm.domain.match import MatchTarget, retrieve
from mcm.imports import _Matcher
from mcm.ports.album_judge import Judgement

TARGETS = [
    MatchTarget(id=1, artist="Blur", title="Modern Life Is Rubbish"),
    MatchTarget(id=2, artist="Blur", title="The Great Escape"),
    MatchTarget(id=3, artist="Various Artists", title="Fabric 19"),
    MatchTarget(id=4, artist="Ladytron", title="Ladytron"),
    MatchTarget(id=5, artist="Burial", title="Untrue"),
]


class FakeJudge:
    """Answers with whatever it was told to, and records what it was asked."""

    def __init__(self, judgement: Judgement | None) -> None:
        self.judgement = judgement
        self.asked: list[MatchTarget] = []

    def choose(self, *, name: str, candidates: list[MatchTarget]) -> Judgement | None:
        self.asked = candidates
        return self.judgement


def matcher(judge: object | None, *, min_confidence: float = 0.6) -> _Matcher:
    return _Matcher(judge=judge, threshold=0.5, candidates=12, min_confidence=min_confidence)


# --- retrieval: recall, not precision ----------------------------------------


def test_retrieval_finds_the_album_through_release_noise() -> None:
    got = retrieve("Blur - The Great Escape [FLAC] {Food CDFOOD11}", TARGETS, limit=3)
    assert got[0].id == 2


def test_retrieval_keeps_siblings_for_the_judgement_to_separate() -> None:
    # Both Blur albums come back; deciding between them is not retrieval's job.
    ids = {t.id for t in retrieve("Blur - The Great Escape [FLAC]", TARGETS, limit=12)}
    assert {1, 2} <= ids


def test_retrieval_finds_a_compilation_on_its_title_alone() -> None:
    # "Various Artists" identifies nothing, so the title has to carry it.
    got = retrieve("VA - Fabric 19 (2004) [FLAC]", TARGETS, limit=3)
    assert got[0].id == 3


def test_retrieval_finds_a_self_titled_album() -> None:
    assert retrieve("Ladytron", TARGETS, limit=3)[0].id == 4


def test_retrieval_returns_nothing_for_an_unrelated_download() -> None:
    assert retrieve("Some Totally Unrelated Thing", TARGETS, limit=12) == []


def test_retrieval_respects_its_limit() -> None:
    assert len(retrieve("Blur", TARGETS, limit=1)) == 1


# --- the policy around a judgement -------------------------------------------


def test_a_confident_judgement_is_taken() -> None:
    judge = FakeJudge(Judgement(TARGETS[1], 0.97))
    assert matcher(judge).match("Blur - The Great Escape", TARGETS) == 2


def test_a_judgement_of_none_is_a_no_match_not_a_fallback() -> None:
    # The string matcher would claim Fabric 19 here; the judgement overrules it.
    judge = FakeJudge(Judgement(None, 0.97))
    assert matcher(judge).match("Sasha - Fabric 99 [FLAC]", TARGETS) is None


def test_low_confidence_lands_in_the_no_match_tail() -> None:
    judge = FakeJudge(Judgement(TARGETS[3], 0.42))
    assert matcher(judge).match("Ladytron", TARGETS) is None


def test_confidence_exactly_at_the_bar_is_taken() -> None:
    judge = FakeJudge(Judgement(TARGETS[1], 0.6))
    assert matcher(judge).match("Blur - The Great Escape", TARGETS) == 2


def test_an_unavailable_judge_falls_back_to_the_string_matcher() -> None:
    # None means the API failed — losing the download would be worse than a fuzzy guess.
    judge = FakeJudge(None)
    assert matcher(judge).match("Blur - The Great Escape [FLAC]", TARGETS) == 2


def test_no_judge_configured_uses_the_string_matcher() -> None:
    assert matcher(None).match("Blur - The Great Escape [FLAC]", TARGETS) == 2


def test_the_judge_is_only_shown_retrieved_candidates() -> None:
    judge = FakeJudge(Judgement(None, 1.0))
    matcher(judge).match("Blur - The Great Escape [FLAC]", TARGETS)
    assert judge.asked and all(t.id in {1, 2} for t in judge.asked)


# --- option labels ------------------------------------------------------------


def test_options_read_as_albums_and_carry_a_no_match() -> None:
    labels = TypeSafeAlbumJudge._labels(TARGETS[:2])
    assert list(labels) == ["Blur — Modern Life Is Rubbish", "Blur — The Great Escape"]
    assert NONE not in labels  # added alongside, not one of the albums


def test_duplicate_albums_get_distinct_options() -> None:
    twice = [MatchTarget(1, "Blur", "13"), MatchTarget(2, "Blur", "13")]
    labels = TypeSafeAlbumJudge._labels(twice)
    assert len(labels) == 2
    assert {t.id for t in labels.values()} == {1, 2}
