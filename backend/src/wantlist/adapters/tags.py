import tempfile
import zipfile
from pathlib import Path

from mediafile import MediaFile

_AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".alac", ".wv"}


class MediaFileTagReader:
    """Reads embedded tags via beets' bundled mediafile (SPEC §13). For a folder it reads the
    first audio file; for a .zip it extracts just the first audio entry to a temp file and
    reads that — so matching doesn't require unpacking the whole archive up front."""

    def read(self, path: Path) -> tuple[str, str] | None:
        if path.is_dir():
            audio = next((p for p in sorted(path.rglob("*")) if _is_audio(p)), None)
            return _tags_of(audio) if audio else None
        if path.suffix.lower() == ".zip":
            return self._read_from_zip(path)
        return None

    def _read_from_zip(self, path: Path) -> tuple[str, str] | None:
        with zipfile.ZipFile(path) as zf:
            member = next((n for n in sorted(zf.namelist()) if _is_audio(Path(n))), None)
            if member is None:
                return None
            with tempfile.NamedTemporaryFile(suffix=Path(member).suffix) as tmp:
                tmp.write(zf.read(member))
                tmp.flush()
                return _tags_of(Path(tmp.name))


def _is_audio(p: Path) -> bool:
    return p.suffix.lower() in _AUDIO_EXTS


def _tags_of(audio: Path) -> tuple[str, str] | None:
    try:
        mf = MediaFile(str(audio))
    except Exception:
        return None
    artist = mf.albumartist or mf.artist
    album = mf.album
    return (artist, album) if artist and album else None
