from pathlib import Path

from wantlist.adapters.beets import BeetsClient

FAKE_BEET = str(Path(__file__).parent / "fake_beet.sh")


def test_owned_release_group_ids_parses_cli_output() -> None:
    owned = BeetsClient(FAKE_BEET).owned_release_group_ids()
    assert owned == {"rg-owned-1", "rg-owned-2"}  # blank line dropped
