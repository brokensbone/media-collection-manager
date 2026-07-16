# D0 reconcile spike — results & verdict

Run: random sample of 80 saved albums (seed 1), real Spotify library + real beets library
(375 owned albums), 2026-07.

## Numbers

| Metric | Value |
|---|---|
| Resolution rate | **86%** (barcode 56% · isrc 12% · text 18% · none 14%) |
| beets coverage (accuracy ceiling) | **98%** (366 of 375 owned albums carry `mb_releasegroupid`) |
| Ownership among resolved | 7 owned, 62 not-owned (of 69 resolved) |

## Verdict: **GO**

Build on the 3-tier chain as speced (§5). Key reads:

- **Barcode-first is the workhorse** (56% alone — exact, one cheap call). Validates the
  central design bet.
- **The 14% unresolved tail is a data problem, not an algorithm one.** Hand-investigated:
  the misses are genuinely absent from MusicBrainz, or aren't real album releases (Spotify
  "singles"), or obscure label comps. No matcher finds a release-group that doesn't exist
  in MB — so the pipeline already finds essentially everything findable.
- **98% beets coverage** — a strong ceiling; almost nothing owned is invisible to the join.
- **Owned matches confirmed correct** on eyeball.

## Consequence: drop the LLM Tier-3 (D16)

§5a/D16 was scoped to rescue a *fuzzy-matchable* tail. This tail is **MB-absent**, not
fuzzy, so an LLM wouldn't move the number. **D16 is not needed.** (It stays available in
principle only if edition-disambiguation false positives later prove a problem — a
different job from what the spike measured.)

## Design refinements the tail implies (product, not algorithm)

1. **Unresolved albums remain first-class wants** — still saved, still wanted; ownership
   just can't be auto-derived, so they stay `wanted` until resolved.
2. **Manual-match escape hatch** — paste a MusicBrainz release-group id/URL for one you
   care about, or mark owned by hand.
3. **Periodic re-resolve** — retry unresolved albums occasionally; MB grows and new
   releases get added over time.

## Remaining check to fully close accuracy

The subtlest failure mode wasn't in the eyeballed set: **edition-mismatch false negatives**
— an owned album resolving to a *different* release-group than the beets copy (deluxe vs
standard, §4) → shows `resolved & not-owned` despite being owned → would wrongly appear in
the buy list. Recommended: scan the 62 `resolved & not-owned` for any you actually own. If
~none, the join is clean.
