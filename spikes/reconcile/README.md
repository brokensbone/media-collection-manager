# D0 · Reconcile / identity spike

Answers the one question that gates the whole build (SPEC §11): **is the Spotify →
MusicBrainz → beets ownership match good enough to build on?** It runs the real 3-tier
resolution (barcode → ISRC cluster → fuzzy text) over a sample of your actual saved
albums and checks each against your beets library, then reports the numbers.

Standalone: read-only Spotify + MusicBrainz + a beets dump. No app, no Postgres.

## What you need

1. **uv** (already installed).
2. **A Spotify app** — create one at <https://developer.spotify.com/dashboard>:
   - note the **Client ID** and **Client secret**;
   - add redirect URI **`http://127.0.0.1:8888/callback`** exactly (loopback IP, *not*
     `localhost` — Spotify rejects `localhost`).
   - No extended access needed; the spike only reads your library (`user-library-read`).
3. **A beets owned dump** — on whichever machine has the library (the server), run:
   ```
   beet list -a -f '$mb_releasegroupid' > owned_rgids.txt
   ```
   Blank lines (albums with no release-group id) are kept on purpose — they let the spike
   measure coverage. Copy `owned_rgids.txt` next to this script.
   *(Or, if beets is on the same machine, skip the file and pass `--beets-cmd beet`.)*

   *For a plumbing test without the real library, generate a synthetic dump with
   [`../../fixtures/beets/build.sh`](../../fixtures/beets/) and use its
   `out/owned_rgids.txt` — but note synthetic ownership isn't a real accuracy signal.*

## Run

```
SPOTIFY_CLIENT_ID=xxx \
SPOTIFY_CLIENT_SECRET=yyy \
MB_USER_AGENT="mcm-spike/0.1 ( you@example.com )" \
uv run reconcile_spike.py --owned-file owned_rgids.txt --sample 80
```

A browser opens → authorize → the run proceeds. MusicBrainz is rate-limited to ~1 req/s
and every response is cached under `.spike/`, so the **first** run of ~80 albums takes
roughly 15–25 min; re-runs are seconds. Set a real contact in `MB_USER_AGENT` — MB blocks
generic agents.

Outputs land in `.spike/out/`: `report.md` (human summary) and `results.json` (raw).

Useful flags: `--sample 0` (all saved albums), `--seed N` (reproducible sample),
`--isrc-cap`, `--text-min-score`, `--beets-cmd`/`--beets-config` (instead of `--owned-file`).

## Reading the result (the §11 decision gate)

- **Resolution rate by tier.** High overall is good. If **text** (Tier 3, fuzzy) is
  carrying the load, that's a yellow flag — the exact-ID tiers aren't biting.
- **beets coverage** = share of owned albums that carry an `mb_releasegroupid`. This is the
  **accuracy ceiling**: albums with no id can never match, however good the Spotify side is.
- **Ownership among resolved** = derived owned vs not-owned.
- **Hard bucket** = unresolved albums; look for patterns (all new? all comps? one label?)
  → tells you whether the tail is ignorable or needs an LLM Tier-3 / manual escape hatch.

**Accuracy needs a human check** (the script can't know ground truth): from the sample
table in `report.md`, hand-verify ~20 you *know* you own and ~20 you *know* you don't,
watching especially for **false positives** (says owned when you're not — the harmful
failure). That plus the numbers above gives the go / no-go and the LLM-Tier-3 call.

Nothing here is committed — `.spike/`, tokens, and dumps are gitignored.
