"""
Build a seeded beets library from a manifest of albums, using tiny silent FLACs tagged
with MusicBrainz ids. Runs inside the Docker image (beets + ffmpeg + mediafile).

Output (to /out): library.db and owned_rgids.txt
  owned_rgids.txt mirrors `beet list -a -f '$mb_releasegroupid'` — one line per album,
  blank for albums with no release-group id (so it doubles as the spike's --owned-file
  and the D2/D5/§14 fixture).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from mediafile import MediaFile

WORK = Path("/work")
OUT = Path("/out")
SRC = WORK / "src"
CFG = WORK / "beets-config.yaml"

CONFIG = f"""\
directory: {WORK/'music'}
library: {OUT/'library.db'}
import:
    move: yes
    write: no
    resume: no
    quiet: yes
    autotag: no
"""


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def silent_flac(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=channel_layout=mono:sample_rate=44100", "-t", "1",
         "-c:a", "flac", str(path)],
        check=True,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    CFG.write_text(CONFIG)
    (WORK / "music").mkdir(exist_ok=True)

    albums = json.loads((WORK / "albums.json").read_text())
    for a in albums:
        adir = SRC / slug(f"{a['albumartist']}-{a['album']}")
        adir.mkdir(parents=True, exist_ok=True)
        for i, title in enumerate(a["tracks"], 1):
            fp = adir / f"{i:02d} {slug(title)}.flac"
            silent_flac(fp)
            mf = MediaFile(str(fp))
            mf.albumartist = a["albumartist"]
            mf.artist = a["albumartist"]
            mf.album = a["album"]
            mf.title = title
            mf.track = i
            mf.mb_albumid = a["mb_albumid"] or None
            mf.mb_releasegroupid = a["mb_releasegroupid"] or None
            mf.save()
        subprocess.run(["beet", "-c", str(CFG), "import", "-A", "-q", str(adir)], check=True)

    dump = subprocess.run(
        ["beet", "-c", str(CFG), "list", "-a", "-f", "$mb_releasegroupid"],
        check=True, capture_output=True, text=True,
    ).stdout
    (OUT / "owned_rgids.txt").write_text(dump)
    n = len(dump.splitlines())
    with_id = len([ln for ln in dump.splitlines() if ln.strip()])
    print(f"Imported {len(albums)} albums -> {n} in library, {with_id} carry a release-group id")
    print(f"Wrote {OUT/'library.db'} and {OUT/'owned_rgids.txt'}")


if __name__ == "__main__":
    main()
