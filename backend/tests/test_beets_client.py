from pathlib import Path

from beets.library import Item, Library

from wantlist.adapters.beets import BeetsClient


def _make_beets_library(tmp_path: Path) -> str:
    """Build a real (tiny) beets library via its API — no audio files needed — and return
    a config path pointing at it. beets is a bundled dependency now, so this is real beets."""
    db = tmp_path / "library.db"
    lib = Library(str(db))
    for title, release_group in [("A1", "rg-1"), ("A2", "rg-2"), ("A3", None)]:
        item = Item(album=title, albumartist="X", title="t", path=f"/fake/{title}.flac".encode())
        if release_group:
            item.mb_releasegroupid = release_group
        lib.add_album([item])
    del lib

    config = tmp_path / "config.yaml"
    config.write_text(f"library: {db}\ndirectory: {tmp_path}\n")
    return str(config)


def test_owned_release_group_ids_from_real_beets(tmp_path: Path) -> None:
    config = _make_beets_library(tmp_path)
    owned = BeetsClient(config=config).owned_release_group_ids()
    assert owned == {"rg-1", "rg-2"}  # the id-less album contributes a blank line, dropped
