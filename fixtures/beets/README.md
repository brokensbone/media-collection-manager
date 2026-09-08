# Seeded beets fixture

A reproducible, tiny beets library built from [`albums.json`](albums.json) — used to
exercise the beets seam without needing the real library. Shared by:

- the **D0 spike** (a synthetic `owned_rgids.txt` to test the beets side — plumbing only,
  not real accuracy);
- **D2 / D5 / §14** integration + E2E tests (a seeded `library.db` to reconcile against).

## How it works

Each album's tracks become **1-second silent FLACs** (via ffmpeg), tagged with MusicBrainz
ids (`mb_albumid`, `mb_releasegroupid`) using `mediafile`, then imported with
`beet import -A` (as-is, no autotag) so beets stores those ids verbatim. One album is
deliberately left with **no** release-group id, so the coverage path (owned album that can
never match) is represented.

## Build

```
./build.sh
```

Builds the Docker image (beets + ffmpeg + mediafile) and writes to `out/` (gitignored):

- `out/library.db` — the seeded beets database (the test fixture).
- `out/owned_rgids.txt` — `beet list -a -f '$mb_releasegroupid'`, one line per album,
  blank for the id-less one. Feed to the spike: `--owned-file out/owned_rgids.txt`.

Edit `albums.json` to change the library. Ids are arbitrary-but-stable UUIDs; tests that
drive the Spotify/MB side just have to resolve to the same ids.
