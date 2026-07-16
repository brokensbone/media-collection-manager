from wantlist.health import check_beets


def test_reachable_when_command_exits_zero() -> None:
    assert check_beets("true") is True


def test_unreachable_when_command_exits_nonzero() -> None:
    assert check_beets("false") is False


def test_unreachable_when_command_missing() -> None:
    assert check_beets("definitely-not-a-real-command-xyz") is False
