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


def test_all_albums_parses_facets(monkeypatch: pytest.MonkeyPatch) -> None:
    sep = beets_mod._SEP
    # One fully-tagged album and one with the facet fields empty (beets emits `0` for a missing
    # year), to prove the split maps positionally and blanks/zeroes become None.
    rows = [
        sep.join(
            [
                "b1",
                "Burial",
                "Untrue",
                "rg-1",
                "2007",
                '12" Vinyl',
                "Hyperdub",
                "GB",
                "album",
                "Dubstep",
            ]
        ),
        sep.join(["b2", "X", "Untagged", "", "0", "", "", "", "", ""]),
        # beets emits the literal template token (e.g. `$media`) for a field it can't resolve on an
        # album — must be treated as absent, not become a bogus "$media" value/crate.
        sep.join(
            [
                "b3",
                "Y",
                "NoMedia",
                "",
                "2020",
                "$media",
                "$label",
                "$country",
                "$albumtypes",
                "$genre",
            ]
        ),
    ]

    def fake_run(argv: list[str], **kwargs: Any) -> object:
        class Result:
            stdout = "\n".join(rows) + "\n"
            stderr = ""

        return Result()

    monkeypatch.setattr(beets_mod.subprocess, "run", fake_run)
    by_id = {a.beets_id: a for a in BeetsClient().all_albums()}

    a = by_id["b1"]
    assert (a.year, a.media, a.label, a.country) == (2007, '12" Vinyl', "Hyperdub", "GB")
    assert (a.secondary_types, a.genre, a.mb_releasegroup_id) == ("album", "Dubstep", "rg-1")
    b = by_id["b2"]  # empty facets and a `0` year all collapse to None
    assert b.mb_releasegroup_id is None and b.year is None and b.media is None
    assert b.label is None and b.country is None and b.secondary_types is None and b.genre is None
    c = by_id["b3"]  # leaked `$…` tokens collapse to None (but a real year still parses)
    assert c.year == 2020
    assert c.media is None and c.label is None and c.country is None
    assert c.secondary_types is None and c.genre is None


def test_import_dir_skips_duplicates_uses_asis_and_traps_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> object:
        captured["argv"] = argv
        # read the layered override while the temp file still exists (unlinked after _run returns)
        captured["override"] = Path(argv[argv.index("--config") + 1]).read_text()

        class Result:
            stdout = ""
            stderr = ""  # the -vv trap reads stderr for the resolved directory

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    BeetsClient().import_dir("/drop")

    argv = captured["argv"]
    # `-vv` (diagnostic trap) then `--config <overlay>` are global opts before the subcommand.
    assert argv[0] == "beet" and argv[1] == "-vv" and argv[2] == "--config"
    assert argv[4:] == ["import", "-q", "--quiet-fallback=asis", "/drop"]
    assert "duplicate_action: skip" in captured["override"]


def test_trap_flags_default_directory_and_passes_the_configured_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HOME", "/root")
    client = BeetsClient()
    good = (
        "data directory: /mnt/ssd4tb/record-library\n"
        "library database: /mnt/ssd4tb/record-library/beets.db\n"
        "library directory: /home/example/.config/beets/library\n"
    )
    with caplog.at_level("INFO", logger="wantlist.adapters.beets"):
        client._trap_import_directory("/drop", good)
    assert "directory ok" in caplog.text and "/home/example" in caplog.text

    caplog.clear()
    bad = "library directory: /root/Music\n"  # beets fell back to its default → the bug
    with caplog.at_level("INFO", logger="wantlist.adapters.beets"):
        client._trap_import_directory("/drop", bad)
    assert "DEFAULT (wrong) library directory" in caplog.text


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
