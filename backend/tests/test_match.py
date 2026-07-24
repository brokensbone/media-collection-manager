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


def test_different_album_by_same_artist_is_not_matched() -> None:
    # A shared artist must not drag a different album onto a funnel album (the bug: a download
    # for Metalhorse attaching to the owned CACTI). The real CACTI download still matches.
    targets = [MatchTarget(id=1, artist="Billy Nomates", title="CACTI")]
    assert (
        best_match("Billy Nomates - Metalhorse (2025) [WEB-FLAC]", targets, threshold=0.5) is None
    )
    assert (
        best_match("Billy Nomates - Cacti (2023) [FLAC CD] {Invada}", targets, threshold=0.5) == 1
    )


def test_plain_download_matches_a_deluxe_edition_but_not_a_sibling() -> None:
    targets = [
        MatchTarget(id=7, artist="Big Special", title="Postindustrial Hometown Blues (Deluxe)")
    ]
    assert (
        best_match("Big Special - Postindustrial Hometown Blues (2024) - WEB FLAC", targets, 0.5)
        == 7
    )
    assert best_match("BIG SPECIAL -2025- NATIONAL AVERAGE (FLAC)", targets, 0.5) is None


def test_unrelated_titles_do_not_match_on_incidental_character_overlap() -> None:
    # Whole-string ratio used to match these (shared spaces/letters/"the"); the title gate rejects.
    targets = [
        MatchTarget(id=1, artist="Film for the Future", title="In Place"),
        MatchTarget(id=2, artist="Pye Corner Audio", title="The Endless Echo"),
    ]
    assert best_match("Blur - The Great Escape [FLAC]", targets, threshold=0.5) is None
    assert best_match("Christine and the Queens - Chris (2018)", targets, threshold=0.5) is None
