from wantlist.domain.match import MatchTarget, best_match

TARGETS = [
    MatchTarget(id=1, artist="Patrick Wolf", title="Lupercalia"),
    MatchTarget(id=2, artist="Burial", title="Untrue"),
]


def test_matches_despite_scene_naming_noise() -> None:
    assert best_match("Patrick_Wolf-Lupercalia-2011-FLAC", TARGETS, threshold=0.5) == 1


def test_no_match_returns_none() -> None:
    assert best_match("Some Totally Unrelated Thing", TARGETS, threshold=0.5) is None


def test_picks_the_better_of_two() -> None:
    assert best_match("Burial - Untrue (2007)", TARGETS, threshold=0.4) == 2
