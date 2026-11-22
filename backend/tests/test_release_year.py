from mcm.adapters.spotify_api import _release_year


def test_spotify_release_year_handles_partial_and_missing_dates() -> None:
    assert _release_year("2026-11-22") == 2026
    assert _release_year("2026-11") == 2026
    assert _release_year("2026") == 2026
    assert _release_year(None) is None
    assert _release_year("unknown") is None
