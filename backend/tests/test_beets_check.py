from wantlist.health import check_beets


def test_bundled_beets_is_runnable() -> None:
    assert check_beets() is True  # beets is a bundled dependency
