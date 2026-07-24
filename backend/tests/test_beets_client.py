import subprocess
from pathlib import Path
from typing import Any

import pytest
from beets.library import Item, Library

import wantlist.adapters.beets as beets_mod
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


def _locked_error(argv: list[str]) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        1,
        argv,
        output="",
        stderr="error: database ... beets.db cannot not be opened: database is locked",
    )


def test_run_retries_when_the_library_is_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(beets_mod.time, "sleep", lambda *_: None)  # no real backoff wait
    calls = {"n": 0}

    def fake_run(argv: list[str], **kwargs: Any) -> object:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _locked_error(argv)  # locked the first two attempts

        class Result:
            stdout = "rg-1\n"

        return Result()

    monkeypatch.setattr(beets_mod.subprocess, "run", fake_run)
    assert BeetsClient().owned_release_group_ids() == {"rg-1"}
    assert calls["n"] == 3  # retried past the two locked attempts


def test_run_does_not_retry_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_run(argv: list[str], **kwargs: Any) -> object:
        calls["n"] += 1
        raise subprocess.CalledProcessError(1, argv, output="", stderr="error: no such command")

    monkeypatch.setattr(beets_mod.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        BeetsClient().owned_release_group_ids()
    assert calls["n"] == 1  # a non-lock error fails fast, no retries


def test_run_gives_up_after_persistent_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(beets_mod.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_run(argv: list[str], **kwargs: Any) -> object:
        calls["n"] += 1
        raise _locked_error(argv)

    monkeypatch.setattr(beets_mod.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        BeetsClient().owned_release_group_ids()
    assert calls["n"] == 5  # initial try + 4 retries
