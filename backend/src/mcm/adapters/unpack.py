import shutil
import zipfile
from pathlib import Path


def unpack(archive_path: str, dest: str) -> None:
    """Stage a watch-dir drop into `dest` (SPEC §13): extract a .zip (guarded against
    zip-slip / path traversal) or copy a loose folder. The original is left untouched here;
    disposition happens after a successful import (see `dispose`)."""
    src = Path(archive_path)
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        shutil.copytree(src, out, dirs_exist_ok=True)
        return

    root = out.resolve()
    with zipfile.ZipFile(src) as zf:
        for member in zf.namelist():
            target = (out / member).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"unsafe path in archive (zip-slip): {member!r}")
        zf.extractall(out)


def dispose(archive_path: str, *, disposition: str, archive_dir: str) -> None:
    """Dispose of the original drop after a successful import (SPEC §13). The zip is ours, so
    unlike the §12 seedbox we may move/delete: archive (default, safest) / delete / leave."""
    src = Path(archive_path)
    if disposition == "leave" or not src.exists():
        return
    if disposition == "delete":
        shutil.rmtree(src) if src.is_dir() else src.unlink()
        return
    Path(archive_dir).mkdir(parents=True, exist_ok=True)  # archive
    shutil.move(str(src), str(Path(archive_dir) / src.name))
