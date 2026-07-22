from pathlib import Path
from typing import Any

import pytest
from beets.library import Item, Library

from wantlist.adapters.beets import BeetsClient


def _make_beets_dir(tmp_path: Path) -> Path:
    """Build a real (tiny) beets library via its API — no audio files needed — in a BEETSDIR,
    with a config that uses a RELATIVE library path (the real-world case that broke: it only
    resolves when beets treats the dir as BEETSDIR). beets is bundled, so this is real beets."""
    db = tmp_path / "library.db"
    lib = Library(str(db))
    for title, release_group in [("A1", "rg-1"), ("A2", "rg-2"), ("A3", None)]:
        item = Item(album=title, albumartist="X", title="t", path=f"/fake/{title}.flac".encode())
        if release_group:
            item.mb_releasegroupid = release_group
        lib.add_album([item])
    del lib
    # relative path — resolves against BEETSDIR, not CWD or the config file's dir
    (tmp_path / "config.yaml").write_text(f"library: library.db\ndirectory: {tmp_path}\n")
    return tmp_path


def test_owned_release_group_ids_via_beetsdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BEETSDIR", str(_make_beets_dir(tmp_path)))
    owned = BeetsClient().owned_release_group_ids()
    assert owned == {"rg-1", "rg-2"}  # the id-less album contributes a blank line, dropped


def test_import_dir_uses_quiet_asis_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> object:
        captured["argv"] = argv
        captured["kwargs"] = kwargs

        class Result:
            stdout = ""

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    BeetsClient().import_dir("/drop")

    assert captured["argv"] == ["beet", "import", "-q", "--quiet-fallback=asis", "/drop"]
