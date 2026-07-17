import zipfile
from pathlib import Path

import pytest

from wantlist.adapters.unpack import dispose, unpack


def test_unpack_zip_extracts_contents(tmp_path: Path) -> None:
    archive = tmp_path / "album.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Album/01.flac", "one")
        zf.writestr("Album/02.flac", "two")
    dest = tmp_path / "staging"

    unpack(str(archive), str(dest))

    assert (dest / "Album" / "01.flac").read_text() == "one"
    assert (dest / "Album" / "02.flac").read_text() == "two"


def test_unpack_rejects_zip_slip(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.flac", "pwned")
    dest = tmp_path / "staging"

    with pytest.raises(ValueError, match="zip-slip"):
        unpack(str(archive), str(dest))
    assert not (tmp_path / "escaped.flac").exists()  # nothing written outside dest


def test_unpack_copies_loose_folder(tmp_path: Path) -> None:
    drop = tmp_path / "Loose Album"
    drop.mkdir()
    (drop / "track.flac").write_text("audio")
    dest = tmp_path / "staging"

    unpack(str(drop), str(dest))

    assert (dest / "track.flac").read_text() == "audio"
    assert (drop / "track.flac").exists()  # source left in place (dispose handles removal)


def test_dispose_archive_moves_into_done(tmp_path: Path) -> None:
    zip_path = tmp_path / "buy.zip"
    zip_path.write_text("z")
    done = tmp_path / "done"

    dispose(str(zip_path), disposition="archive", archive_dir=str(done))

    assert not zip_path.exists()
    assert (done / "buy.zip").read_text() == "z"


def test_dispose_delete_removes(tmp_path: Path) -> None:
    zip_path = tmp_path / "buy.zip"
    zip_path.write_text("z")
    dispose(str(zip_path), disposition="delete", archive_dir=str(tmp_path / "done"))
    assert not zip_path.exists()


def test_dispose_leave_keeps(tmp_path: Path) -> None:
    zip_path = tmp_path / "buy.zip"
    zip_path.write_text("z")
    dispose(str(zip_path), disposition="leave", archive_dir=str(tmp_path / "done"))
    assert zip_path.exists()
