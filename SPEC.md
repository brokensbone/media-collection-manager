# Project Spec — (working title: "wantlist")

> Status: **MVP built** (ROADMAP D0–D9 complete). This spec is the design of record;
> where implementation refined a decision, the relevant section notes "as built". Remaining
> work is deploy (D10) and the post-MVP increments (D11+).
>
> **Delivery plan:** [ROADMAP.md](ROADMAP.md) turns this spec into sequential,
> green-light-able deliverables, each with a concrete "done" gate.

## 1. The problem (one sentence)

Discovery happens on Spotify, ownership lives in beets, and the gap between the two
is manual friction — so wants get forgotten, the owned library stagnates, and I stay
on Spotify by default. **The compounding loop is the enemy.**

## 2. What this is (and isn't)

**Is:** a *smart want-list, fed by my own Spotify activity, that nudges me*. It
captures things I've engaged with, continuously tells me whether I already own each
one, and prompts me with a few reactive nudges (see §6). It never lets a want be
silently forgotten. **Not a recommender** — I do plenty of discovery myself; this
tool's job is to stop discovery leaking away, not to generate more of it.

**Is not:**
- Not a library manager — **beets stays the library**, source of truth for what I own.
- Not a player — **Navidrome / mpd stay for playback**.
- Not an auto-acquirer — **acquisition stays manual.** The tool tracks intent and
  ownership; I do the buying/downloading. (Explicit decision, not a limitation to
  fix later. It sidesteps the old system's brittle auto-match-then-download risk.)

Design principles:
- **Thin brain over beets.** Don't reinvent identity resolution or storage that beets
  already does well.
- **Deployment-agnostic.** The app knows only two things about its environment, both
  from config: it needs a **PostgreSQL backend** (host/port/db/user/password) and a way
  to **run the beets CLI** (a configurable command/path). It has no knowledge of *where*
  it runs. My own hosting (blink + partridge) is a *reference deployment* (§8b), not a
  requirement — anyone with a Postgres and a beets install can run it.

## 3. The loop this closes

```
        ┌─────────────┐     ┌──────────────────────────────────────────┐
        │   CAPTURE   │◄────┤ PLAY HISTORY: poll recently-played, build  │
        │             │     │ a local scrobble log → powers 6a (§4a)     │
        └──────┬──────┘     └──────────────────────────────────────────┘
               │  Spotify saves/likes (my own activity) — the raw firehose
               ▼
        ┌─────────────┐
        │   NUDGE     │  3 reactive prompts (see §6): "do I like it?", "new by
        │             │  this artist", "more of this artist's catalogue"
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │  WANT-LIST  │  a save becomes a *want* only after I say so (curation).
        │             │  Each want: canonical identity + provenance + state
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │  RECONCILE  │  do I already own this? (continuous check against beets)
        └──────┬──────┘
               ▼
     not owned │ owned ──────────────► mark OWNED, drop off the active list
               ▼
        ┌─────────────┐
        │  I ACQUIRE  │  manual, but assisted: one-click "Buy on Bandcamp"
        │             │  link per want (§6.5). Tool links, never buys.
        └──────┬──────┘
               ▼
        files land in beets inbox → import → RECONCILE flips it to owned. Loop closed.
```

(The manual "land" step — get files into beets — can be automated: the §12 Transmission
auto-land extension for seedbox torrents, and the §13 watch-dir importer for Bandcamp
zips and dropped folders.)

The magic is that **reconcile runs continuously**. The day a FLAC of a wanted album
lands in beets — however it got there — the want auto-resolves. Nothing to remember.

## 4. Core concepts / data model

Album-centric (this is the one thing the old system got right and confirmed works).
Track-level is a possible later refinement, not the MVP unit.

Persisted in **PostgreSQL** (connection from config, §8a) — the tool holds no local
SQLite of its own. The only SQLite in the picture is beets', reached solely via the
beets CLI (§5).

Two conceptual layers matter here: a raw **save** (low-signal, from the Spotify
firehose) is distinct from a curated **want** (something I've decided I want to own,
via the §6a verdict). Could be one table with a state field, or two — see open Qs.

**`Album` record** — the central entity:
- **Identity (the spine):** MusicBrainz **release-group** ID as canonical. Source IDs
  (Spotify album id, etc.) hang off it as aliases.
- **Provenance:** how it entered — spotify-save / artist-watch (6b) / backfill (6c) /
  manual.
- **State (the curation + ownership lifecycle):**
  `suggested` → *(Save)* `saved` → *(6a verdict)* `wanted` → *(mark as ordered)*
  `acquiring` → `owned`, plus `dismissed`. One linear field tells the whole story.
  **Entry state depends on provenance:** a Spotify save enters at `saved` (already in my
  library); a 6b/6c discovery enters at `suggested` (a candidate I haven't saved). Notes:
  - **`suggested`** = surfaced by the artist-watch (6b) / backfill (6c), *not* yet in my
    Spotify library. Lives in the Releases worklist (§8d). From here: **Save** → `saved`
    (writes to Spotify) · **Want** → `wanted` (also saves; skips `saved`) · **reject** →
    `dismissed`.
  - **De-dup is essential** (everywhere new albums enter, not just 6b). The Album table
    doubles as the **seen-ledger**: discovery and every ingest de-dup against the *whole*
    table by release-group / Spotify id, so nothing already saved/wanted/owned/dismissed
    is re-created or re-suggested. No special reissue handling — a reissue is simply a
    distinct release-group and treated as its own album.
  - **`acquiring`** = bought/ordered but not yet landed in beets. Keeps ordered albums
    out of the Acquire worklist (§8d) so they stop nagging. `ordered_at` timestamps it.
  - **`owned` is *derived* from reconcile, not set by hand.** Reconcile promotes
    `wanted` *or* `acquiring` → `owned` when it finds a match. `acquiring` is skippable:
    importing something you never marked as ordered goes `wanted` → `owned` directly.
  - **`dismissed`** = terminal "don't resurface", reachable from `suggested` (rejected a
    suggestion — reissue/single) *or* from `saved`/`wanted` (dropped at verdict / changed
    mind). No separate "rejected" state — **provenance** distinguishes the two reasons,
    and the Dismissed view can filter on it.
  - **Reversible:** cancelling an order is `acquiring` → `wanted`.
  - (`acquiring` chosen as a state, not a flag: a single linear field is fewer things to
    look at, and reversibility doesn't distinguish the two.)
- **Verdict timing fields:** saved-at, verdict-at (null = still awaiting judgement).
  Drives the 6a "surface saves older than N days with no verdict" query.
- **Ownership link:** the owned beets album (else null), with a **source**:
  - `auto` — derived by reconcile from a release-group match; recomputed every pass (§5).
  - `manual` — a link I made by hand to a specific beets album; **sticky** — reconcile
    never overwrites or clears it (only re-surfaced if that beets album disappears).
  Either sets state `owned`. The manual link is the **universal fallback** when
  release-group ids don't match or don't exist — edition mismatches (saved the standard,
  own the deluxe) and MB-absent albums (§5). It needs no MB id at all.
- **Acquisition hints (optional):** candidate source links (Bandcamp, etc.), added
  manually or scraped read-only. Never acted on automatically.

**Auth/credentials store** (small, separate): the Spotify refresh + access tokens, access
expiry, and — critically — **`spotify_authorized_at`**, the timestamp of the last full
authorization. Needed because refresh tokens now expire at 6 months and carry no
issuance time of their own (§8c). **Stored plaintext in Postgres** (single `spotify_auth`
row) — a deliberate choice for a single-user LAN deployment; encryption-at-rest was
considered and declined. (`client_id`/`client_secret` live in config, not the DB.)

### 4a. Play history (listening data) — a local store the tool builds itself

Spotify has **no play-count API** and no deep-history endpoint. `recently-played`
returns only the **last 50 tracks**. So we can't query "have I listened to this?" on
demand — we have to *accumulate* it:
- **Poll `recently-played` on a schedule** (every ~30 min) and append to a
  play-history table in Postgres (a mini scrobble log). Over time this answers "how many
  times / over how many days have I played tracks from saved album X?".
- **DECIDED: polling only from install, no GDPR backfill.** Accepts that the history
  (and therefore the 6a "you've listened" trigger) is quiet for the first few weeks
  while it fills up. See §6a for how v1 degrades gracefully in the meantime.
- **Future alternative:** if I ever scrobble to ListenBrainz/Last.fm, read history from
  there instead — richer and more "own my data". Keep the play-history interface
  source-agnostic so this is swappable. (GDPR-export backfill also remains a later
  option if the cold-start proves annoying.)

This store is what upgrades 6a from a crude timer into "you've actually heard this."

### 4b. Cover art — fetched once, kept, as Postgres blobs

**DECIDED: keep and *own* the art** — fetch each image once and retain it, so it survives
the source later changing or pulling it. It's retained data, not throwaway cache.

- **Storage: blobs in Postgres**, in a **dedicated `album_art` table** separate from
  `album` (so the large bytea column never weighs on hot album-row reads, and it can be
  split to its own schema/DB later without touching the rest). One row per album (× size
  if we keep more than one). Keeps deployment to a single backend — **no writable cache
  volume needed** (dropped from the §8a contract): just Postgres + beets.
- **It's owned data, so it's retained** (and belongs in backups). Because it's separated
  into its own table, backup size stays *manageable by choice* — back it up on its own
  cadence, or split it to a dedicated schema/DB when it grows. (This is the deliberate,
  managed version of the earlier backup-bloat worry.)
- **Don't hotlink** Spotify/CDN image URLs from the browser regardless: they rotate/expire,
  break offline, leak the browser to Spotify's CDN (privacy), and defeat the point of
  owning them. Always self-serve.
- **Serving:** one uniform route (e.g. `/art/<album-id>`) for every state, backed by a
  `bytea` read. Art is immutable per album, so set `ETag` + long/`immutable` `Cache-Control`
  from day one — cheap, and it kills repeat fetches. **If serving ever feels slow, put a
  cache layer in front** (reverse-proxy/CDN or on-disk) — deferred until needed.
- **Sources, best-available at fetch time:**
  - not-yet-owned (`suggested`/`saved`/`wanted`/`acquiring`): **Spotify album images**
    (available from ingest — needed for triage) and/or **Cover Art Archive** via the MB
    release-group id (§5), which fits the own-data ethos.
  - `owned`: art also exists in the **beets** library (embedded + `cover.jpg`); a source we
    can (re)fetch from, not a second serving path — keep the one route.
- **Fetch async at ingest** (a background job filling missing art — exactly
  spotify-scripts' `ArtworkTask`, now writing to `album_art` instead of a dir), with a
  placeholder until stored. Keep one medium image (~300px) and let CSS scale to the ~48px
  list thumbnail (§8e); add a stored small thumbnail later only if list payloads feel heavy.

## 5. Reconciliation — fixing the old system's weakest link

The old `beetsmatch.py` matched Spotify↔beets with `fuzzywuzzy` string ratios over
title tokens and a `>70` cutoff. That's why it only "sort of worked" — reissues,
`feat.`, "Deluxe Edition", and various-artists comps all break it.

**Access beets via the CLI, NOT direct SQLite.** Hard-won lesson: spotify-scripts read
the beets SQLite db with raw concurrent connections and it **locked constantly**. The
beets CLI serialises access through beets' own connection handling. Since the tool's own
state now lives in Postgres (§8), the beets CLI is the *only* place we touch beets — no
raw SQLite anywhere.

**New approach: MusicBrainz IDs as the join key, fuzzy only as last resort.**
- beets already stores `mb_albumid` / `mb_releasegroupid`. If a Want has an MB
  release-group id, ownership is an **exact match** — no fuzzing.
- **Reconcile mechanism (cheap + lock-safe):** one call —
  `beet list -a -f '$mb_releasegroupid'` — dumps every owned release-group id. Load into
  a set, diff wants against it in memory. Single subprocess per reconcile pass, not one
  query per want. (Fall back to `beet list -a mb_releasegroupid:<id>` for spot checks.)
- Getting an MB id for a Spotify album (Spotify doesn't hand these out) — three tiers,
  best-to-worst:
  - **Tier 1 — Barcode (UPC).** Spotify album `external_ids.upc` → MB
    `release?query=barcode:<upc>` → release-group. One call per album, exact when it hits.
  - **Tier 2 — ISRC clustering.** Each Spotify track has an ISRC (stable per *recording*,
    survives reissues) → MB `recording?query=isrc:<isrc>&inc=release-groups`; the
    release-group holding the most of the album's ISRCs (≈ matching track count) wins.
    Robust across editions; multi-step and rate-limited.
  - **Tier 3 — Fuzzy text.** MB search by artist+album. MB's search/disambiguation beats
    local fuzzy matching, but it's still the fuzzy tier — flag low-confidence. **This is
    the tier an LLM could improve — see §5a.**
- **Resolve once, reconcile forever.** Identity resolution (Spotify→release-group) runs
  **once per album at ingest** and the result is stored. Ownership reconcile is then a
  pure deterministic join on the stored id, run continuously and cheaply. Keep the
  expensive/fuzzy step off the hot path.
- **Unresolved is a first-class state, not a failure.** The D0 spike (§11) found ~14% of
  saved albums don't resolve — mostly because they're **absent from MusicBrainz** or
  aren't real album releases, *not* a matching weakness. So an unresolved album stays a
  normal `wanted` (you still saved it); ownership just can't be *auto*-derived.
- **The manual link makes the loop always closable — MVP.** Because MB is spotty and
  editions diverge, the deterministic rgid join can't be the only way to reach `owned`.
  A **manual link from a want to a specific beets album** (§4, sticky) is the universal
  fallback: it needs no MB id, and it handles both edition mismatch (saved standard, own
  deluxe) and MB-absent albums (buy it → import to beets → link the want → owned). A
  *minimal* form of this ships in MVP — without it, those albums could never leave the
  buy list even once owned.
- **Assisted tail handling — post-MVP (ROADMAP D17):** fuzzy-suggested link candidates
  (match the want against the beets library so linking is one click — fuzzy is safe here
  because a human confirms), a proactive "you might already own this (different edition)?"
  hint in Acquire, and a **periodic re-resolve** that retries unresolved albums as MB
  grows. No LLM needed — the tail isn't fuzzy-matchable, just sometimes absent.
- **Beets is a bundled dependency; the app runs its own `beet`.** beets is a Python
  package (pinned in our deps), so we don't rely on an external binary being provided.
  It runs behind a small "beets query" seam — v1 needs essentially **one operation**,
  "list all owned release-group ids" — via the CLI (not raw SQLite; the locking lesson
  above). Resolves the earlier mount-vs-sidecar question in favour of **bundle + mount**.
  - **The one config knob is a path to the beets config** (`-c` / `BEETSDIR`), whose
    `library:` / `directory:` point at the **mounted** `library.db` (and, for imports, the
    music dir). So the deployment requirement is: *mount the beets library where the app
    can read it, and point the config at it*. (If beets ever genuinely had to be remote and
    unmountable, we'd add a seam then — but that's not a case we have, so no knob for it.)
  - **Bonus:** because beets is bundled, CI and tests run **real beets** (build a tiny
    library via its API — no audio needed — and query it), not a stub.

### 5a. Would an LLM do the matching better? (consideration)

Short answer: **only for Tier 3, and only as an adjudicator that's allowed to abstain.**
The three tiers split cleanly into two kinds of work:

- **Tiers 1 & 2 are exact-ID joins** (barcode, ISRC → release-group). These are already
  fast, free, instant, and *reproducible*. Putting an LLM here is strictly worse: it adds
  cost, latency, and — the dealbreaker — **non-determinism** to cases that are already
  perfect. The worst outcome for this tool is a **false positive** (says *owned* when I'm
  not → the album never reaches the want-list → I never buy it), and an LLM can
  confidently hallucinate a match. Don't let the core correctness depend on model temp /
  version drift. **Keep these deterministic.**
- **Tier 3 is fuzzy human judgment** — "is Spotify's *Album (Deluxe)* the same
  release-group as beets' *Album*?", feat.-artist noise, various-artist comps, unicode /
  transliteration, "The Beatles" vs "Beatles". This is exactly where `fuzzywuzzy` fell
  over and exactly what LLMs are good at. An LLM-as-judge — given the candidate MB
  release-groups (or tool access to query MB) — can adjudicate the ambiguous tail far
  better than string ratios. **Crucially it must be able to say "not sure" → route to the
  human triage inbox** rather than guess. A confident-but-wrong LLM here is just a
  fancier false positive.

**Whether to build the LLM tier at all is a decision the spike (§11) gates.** If Tiers
1+2 already cover ~95%, the cheapest good design is: exact-match the bulk, dump the small
tail straight into the human triage inbox, skip the LLM entirely. If the tail is fat and
an LLM meaningfully shrinks the manual work, it's worth adding. Measure first.

**Resolved by D0 (§11): not building it.** The spike showed the unresolved tail is
**MB-absent / not-real-albums, not fuzzy-matchable** — an LLM can't resolve a release-group
that doesn't exist. So the LLM Tier-3 is **dropped** (ROADMAP D16 → D17); the tail is
handled by manual-match + re-resolve (§5) instead. Reconsider only if edition-mismatch
false positives later emerge as a distinct problem.

**If built:** run it as a *batch* over unresolved albums (a scheduled job / skill — fits
the existing `blink` scheduler and skills setup), never inline on the continuous
reconcile. It writes a resolved release-group id (with a confidence + provenance flag)
back to the album, after which reconcile treats it like any other exact match. This keeps
the "resolve once, reconcile forever" split intact: the LLM only ever touches
identity resolution, never the ownership check.

## 6. The three nudges (this replaces "discovery engine")

No recommender. Three reactive prompts, all driven off *my own activity* and all
buildable on Spotify endpoints that survived the Nov-2024 deprecations
(`saved-albums`, `artist's albums`, `followed-artists` are all fine; only
`recommendations`/`related-artists`/`audio-features` died, none of which are needed).

### 6a. "Do I like it?" — the verdict prompt  *(NEW — old system had nothing like this)*
I save stuff constantly and low-signal. A raw save is *not* yet a want. Re-surface the
saved album and ask for a verdict: **keep → becomes a want-to-own** / **drop →
dismissed, don't resurface**. This is the curation gate that turns the firehose into an
intentional want-list.

Crucially, **don't prompt right after saving** — I haven't heard it yet. Two
complementary triggers fire the prompt (both powered by the §4a play-history store):

- **"You've listened" trigger** — the album has accrued enough plays (e.g. ≥N distinct
  tracks played, or plays spread over ≥M days). Now I can give a real verdict. This is
  the primary, higher-quality signal.
- **"You forgot about it" trigger (safety net)** — saved > T days ago with little/no
  plays. These are the ones that get lost in the stream of new saves. Surface them as
  *"you saved this and never really played it — give it a spin, or drop it?"* so nothing
  quietly rots in the backlog.

**DECIDED defaults:** *listened enough* = ≥4 distinct tracks played **or** plays
spanning ≥3 days; *forgotten* = saved ≥21 days ago with <2 tracks ever played. All
tunable in config.

**Cold-start note (consequence of polling-only history, §4a):** for the first few weeks
the "you've listened" trigger has little data, so 6a will fire mostly via the
time-based "forgotten" trigger. That's fine — the safety net works from day one; the
smarter listened-based prompting simply switches on as history accumulates. v1 is
usable throughout.

### 6b. "Something new by this artist" — the release watch  *(old `artistwatch.py`, re-keyed)*
Spotify is genuinely bad at telling me about new releases. Watch artists I care about
and surface their new albums as candidate wants.
- **DECIDED seed set: both kept-album artists AND followed artists** (union). Kept-album
  artists are the strongest signal but need 6a to have produced verdicts first; folding
  in followed artists gives coverage from day one before that data exists. De-dupe the
  union. Expect some noise from the followed side — acceptable.
- **Mechanism — baseline, then new only (as built, D12).** An artist's *first* watch
  **baselines** it: the whole current catalogue is recorded in a `seen_release` ledger and
  **nothing is surfaced** — so becoming interested in an artist never floods Releases with
  their back-catalogue. Every later poll surfaces only album ids not already in the ledger,
  i.e. genuinely new releases since the baseline. (This supersedes the original "surface
  the whole catalogue" idea and the separate §6c backfill.)
- **Surfaced as the "Releases" worklist (§8d)**, at the front of the funnel. Per-item
  actions:
  - **Save** → save the album to my Spotify library, entering the normal `saved` → Decide
    (§6a) flow. Keeps `saved` meaning "in my Spotify library".
  - **Want** → *also saves*, then jumps straight to `wanted`, skipping the verdict (I
    already know I want it). A `wanted` album is therefore always also saved.
  - **Dismiss** → not interested, don't resurface (so the worklist empties).
- **First Spotify write.** Save/Want call `PUT /me/albums`, which needs the
  **`user-library-modify`** scope — a new scope, and the app's first mutation of Spotify
  state (everything else is read-only). Still user-initiated per item, never automatic.
- Not in v1 (see §9) — this is increment two.

### 6c. "More of this artist's catalogue" — the backfill  *(DROPPED)*
Originally: on keeping an album, fan out the artist's whole back-catalogue as suggestions.
**Dropped in D12 by decision:** surfacing old catalogue is unwanted noise — becoming
interested in an artist should only ever surface their *new* releases going forward, not
their history. The 6b baseline (above) records the existing catalogue as seen precisely so
it *isn't* surfaced. If "browse an artist's catalogue to buy" is ever wanted, it'd be a
pull action (search on demand), not a push into the worklist.

### On "recheck occasionally"
Two distinct scheduled loops, both cheap:
1. **Re-poll Spotify** for new saves and for watched-artist new releases (6b).
2. **Re-reconcile** every want against beets (§5) so newly-owned albums auto-resolve.
The old system faked this by brute-force re-running the *entire* pipeline ~5×/day; here
it's just two targeted jobs.

## 7. Acquisition assist (purchase links) — attacking the core pain directly

The README's central complaint: *"it feels like WORK to move from discovering to
buying/downloading, so I forget."* The single highest-leverage feature is therefore a
**one-click "Buy on Bandcamp" button next to every want.** Bandcamp first (sells FLAC,
pays artists, fits the own-my-data ethos); fallbacks for what isn't there.

Reality of the integrations:
- **Bandcamp has no usable public API** (closed years ago). So:
  - **v1 (robust, ToS-safe): deterministic search URL** — `bandcamp.com/search?q=<artist
    album>`. One click, always works, zero scraping. Good enough to kill the friction.
  - **Enhancement (optional, brittle): scrape** the search result to deep-link the exact
    album page, or confirm availability. Grey-area + fragile — only if v1 proves worth it.
- **Fallbacks** for albums not on Bandcamp, also as search links: Qobuz (FLAC),
  artist's own site, or a plain web search. Prefer Bandcamp; show fallbacks secondarily.
- **Manual override:** the `acquisition hints` field (§4) lets me paste a known purchase
  URL, which the UI then shows as the primary buy button.

Hard line (unchanged): the tool **links, never buys**. No stored payment, no auto-purchase.

## 8. Interface & stack

**DECIDED: standalone Python backend + JS SPA frontend.** Python sits closest to beets
(CLI) and the HTTP APIs; the SPA gives a snappy triage UX (artwork grids, quick
keep/drop). Backend exposes a JSON API the SPA consumes. Concrete stack in §15.

- Shape: FastAPI backend + a React SPA (§15). State (wants + play-history + art) in
  **PostgreSQL**; beets reached via the CLI seam (§5). No local SQLite of its own.
- Scheduled jobs (poll saves, poll recently-played, later poll watched artists,
  reconcile) via the app's own scheduler/cron — not tied to any host's scheduler.
- Core views: the active want-list (not-yet-owned, each with a Buy-on-Bandcamp link),
  a triage inbox (6a verdicts + later 6b/6c suggestions to accept → want / dismiss),
  and owned/history.
- **Later: notifications.** Ping me (Slack? push?) when a want auto-resolves to owned or
  N things are waiting to triage. Not v1.

### 8a. Environment contract (what the app requires) + config

The app is **deployment-agnostic**: it needs exactly two things from its environment,
both supplied by config (env vars / config file). Nothing else about the host is known
to the code.

| Requirement | Config | Notes |
|---|---|---|
| PostgreSQL backend | host, port, database, user, password (or a single `DATABASE_URL`) | The app runs its own migrations on the given database. |
| Beets | beets config path (points at the **mounted** `library.db` + music) | beets is **bundled** in the image (a pinned dep); mount the library where the app can read it (§5). |
| Spotify API | client id/secret, **redirect URI** (public HTTPS, registered in the Spotify dashboard), token store, **overridable base URL** | Authorization Code flow via a thin httpx adapter (§15); see §8c for redirect-URI rules and 6-month re-auth. Read-only scopes for v1; **`user-library-modify`** added when §6b lands. Base URL overridable so E2E can point at a stub (§14) — likewise MB/CAA. |
| Tunables | 6a thresholds, poll intervals, Bandcamp/base URLs, re-auth warning lead time | Sensible defaults; all overridable. |

If those are satisfied, the app doesn't care whether it's in Docker, a VM, bare metal,
one host or three.

### 8b. Reference deployment (my setup — illustrative, not required)

How *I* intend to satisfy the §8a contract. None of this is baked into the app.
- App runs as a container in the **`blink`** docker-compose stack, behind Traefik/TLS.
  Traefik also gives the app its public HTTPS domain — which is what the Spotify redirect
  URI needs (§8c).
- Postgres is the existing instance on **`partridge`**; I create a dedicated DB + writer
  role there (following the `lab` repo `scheduler-db.nix` pattern) and point the app's
  `DATABASE_URL` at it. blink↔partridge share the **LAN (`10.4.1.0/24`)**, so a `pg_hba`
  rule for that CIDR (as `postgres-readonly.nix` already does) is the connection path;
  Tailscale is an optional fallback.
- Beets: the container carries `beet` + read access to the beets library (mount vs
  sidecar TBD — the §5 open item), so the beets command is plain `beet`.

### 8c. Spotify auth & the 6-month re-authorization requirement

**New constraint (verified against Spotify docs, 2026).** Spotify refresh tokens now
**expire after 6 months** (announced 18 Jun 2026; enforced for existing apps from
20 Jul 2026; tokens older than 6 months are invalidated on next use). On expiry the token
endpoint returns **`400 invalid_grant`**; recovery means sending the user through the
authorization-code flow again. The re-auth is interactive (user signs in) but
**low-friction — previously approved scopes carry over**, so it's effectively one click,
no re-consent screen. Applies to user tokens (Authorization Code / PKCE), not
client-credentials.

**Why this matters here:** spotify-scripts assumed a *permanent* headless refresh token —
that assumption is now dead. Because this tool is fundamentally background polling, a
silent 6-monthly expiry would quietly break *everything*. So a re-auth flow is
**v1-critical, not deferred.**

Design:
- **Flow:** Authorization Code **with client secret** (we have a server-side backend;
  PKCE not needed). Our thin httpx adapter (§15) handles the token exchange + refresh; we
  persist the tokens + `spotify_authorized_at` (§4) since refresh tokens expose no
  issuance time.
- **The web UI makes re-auth painless** (we're building one anyway): show a persistent
  "Spotify: connected / reconnect" status. On `invalid_grant`, **pause the polling jobs**
  and surface a prominent **"Reconnect Spotify"** button that runs authorize → callback →
  store-new-token.
- **Proactive, not just reactive:** using `spotify_authorized_at`, warn as the 6-month
  mark approaches (banner now; a notification later) so re-auth happens *before* jobs
  fail, not after. `re-auth warning lead time` is a config tunable (§8a).

Callback / redirect URI (the "think about callback URLs" bit):
- **Redirect-URI rules (Spotify, since Apr 2025):** must be **HTTPS** except loopback;
  **`localhost` is banned** — use explicit `http://127.0.0.1:<port>` / `http://[::1]:<port>`
  for local dev.
- **Production:** a stable public HTTPS callback on the app's own domain, e.g.
  `https://<app-domain>/auth/spotify/callback`. It's **config** (deployment-agnostic,
  §8a), but whatever domain a deployment uses **must be registered as a redirect URI in
  that deployment's Spotify app** (manual dashboard step). Since Spotify client id/secret
  are per-deployer anyway, each deployment registers its own callback — no shared-domain
  problem.
- **Local dev:** `http://127.0.0.1:<port>/auth/spotify/callback`.

### 8d. Web UI — views & worklists

**Framing:** the app is essentially a **set of worklists** — action inboxes over the
album state lifecycle (§4). Each worklist is a query over state + trigger conditions, each
item has *one clear action that removes it*, and every queue is meant to be
**inbox-zero-able**. That directness — "here's what needs you, act, it's gone" — is the
UX expression of the whole mission (stop music leaking away). Around the worklists sit a
few browse/reference views and a persistent status.

**Home / dashboard** — at-a-glance "what needs me": a count/badge per worklist (e.g.
*"2 new · 3 to judge · 12 to buy · 2 to import"*) plus the Spotify connection status. The
entry point into the queues. The worklists read left-to-right as the **funnel**: new
releases → decide → acquire → import.

**Worklists (pending actions), in funnel order:**

1. **Releases** — the §6b new-release watch: albums in the **`suggested`** state (found by
   the artist-watch, not yet in my library). At the *front* of the funnel: it feeds saves
   rather than draining them. Item: artwork, artist/album, which watched artist, release
   date. Actions: **Save** → `saved` (writes to my Spotify library), enters the Decide
   flow · **Want** → `wanted` (*also saves*, skips the verdict) · **Dismiss** →
   `dismissed`, don't resurface. (Save/Want are the app's first Spotify *writes* —
   `user-library-modify` scope, §6b.) **Post-v1** — arrives with the §6b increment.
2. **Decide** — the §6a verdict queue. Albums in `saved` where a 6a trigger has *fired*
   (listened-enough or forgotten) with no verdict yet. **Shows only what's ready to
   judge** — the wider saved backlog that hasn't tripped a trigger stays out, by design
   (don't nag prematurely). Item: artwork, artist/album, *why it surfaced* ("played 5
   tracks" / "saved 24 days ago, never played"), an open-in-Spotify link. Actions:
   **Keep** → `wanted` · **Drop** → `dismissed` · **Snooze** (not heard it yet).
3. **Acquire** — albums in `wanted`. Item: artwork, artist/album, **Buy on Bandcamp**
   (§7) + fallback links + paste-a-URL; a **Mark as ordered** action that moves it to
   `acquiring` (§4) — dropping it out until reconcile flips it `owned` (cancel-order
   returns it to `wanted`); and a **Link to library / mark owned** action — search beets
   and pick the album that satisfies this want (a sticky manual link, §4/§5) for edition
   mismatches or MB-absent albums the rgid join can't catch. (D17 adds fuzzy-suggested
   candidates + a "possibly already owned?" hint here.)
4. **Import** — **extension-only (§12/§13); absent in v1.** Detected downloads
   (Transmission completions / watch-dir drops) awaiting the Import click. Item: source,
   matched want (or "no match → import as new owned"), **Import** button. In v1 landing is
   fully manual and reconcile flips `owned` with no queue at all.

**Browse / reference (not action queues):**

5. **Library / all** — the full table, filterable by state / artist / provenance / date.
   The "everything" behind the worklists.
6. **Owned / recently landed** — what's owned (linked to beets) + the log of wants that
   resolved. The library visibly growing — the point of the whole thing.
7. **Dismissed** — dropped albums, for the occasional un-dismiss.

**Persistent status:**

8. **Spotify connection** (§8c) — a persistent header state: connected / "reconnect in N
   days" / **Reconnect now**. Critical: if this lapses, *every* worklist silently stops
   filling. Shown on the dashboard and as a banner as re-auth nears/needed.
9. **Settings** — thresholds, poll intervals, reconnect. Minimal.

**v1 cut:** dashboard + **Decide** + **Acquire** + **Library/all** + **Owned** + the
Spotify status/banner. The **Releases** queue arrives with §6b and the **Import** queue
with the §12/§13 extensions. Dismissed and Settings are thin.

### 8e. UI aesthetic & interaction

**Direction: sharp, dense, quiet — as fuss-free as possible.** The reference frame is
*Linear / a spreadsheet / a terminal*, **not Bootstrap or Material**. The app is worklists
(lists of data), so the look serves fast scanning and action, not decoration.

Principles:
- **Density first** — compact rows, tight-but-legible spacing; content dominates the screen.
- **Sharp** — `border-radius: 0` throughout. Square buttons, inputs, thumbnails. No pills,
  no bulges.
- **Flat** — structure from **1px rules + whitespace**, not shadows, elevation, or
  gradients.
- **Restrained colour** — near-monochrome base + **one accent**, used sparingly for primary
  actions and the active/selected row. State shown by a small dot / text label + column
  position, **never a chunky coloured badge**.
- **Type does the work** — a tight scale; **grotesque sans for text**, **monospace for
  data**, **tabular figures** so numeric columns align.
- **Lists are the surface** — every worklist is a dense table (`thumb · artist – album ·
  context · inline actions`), rendered by **one shared row component** across all views.
- **Fast & quiet** — instant interactions, minimal/no animation; **keyboard-first triage**
  (navigate + keep/drop/dismiss without the mouse). This is the real "fuss-free".
- **Chrome-light** — a thin top strip (worklist counts + Spotify status), no fat nav bar.

Decisions:
- **Theme: both, theme-aware.** Follow the OS with a manual toggle. Implement via **design
  tokens** (CSS custom properties) so light/dark is a variable swap, not duplicated CSS.
- **Type: sans for text, mono for data.** Grotesque sans (system-ui / Inter) for labels &
  titles; monospace for IDs, counts, dates; tabular figures for aligned columns.
- **Artwork: small square thumbnails, ~48px** (a touch bigger than 40 — recognisable
  without hurting density; flex ~48–56px). Square (sharp), one per row.

Implementation note: a small **design-token layer** (colours, spacing, type scale) drives
both themes and keeps the SPA consistent. **No CSS framework** (Bootstrap/Material would
fight this aesthetic) — hand-rolled CSS or a headless/unstyled component approach fits.

**Reference mockup:** [`mockups/decide-worklist.html`](mockups/decide-worklist.html) — a
self-contained, theme-aware mock of the Decide worklist in this aesthetic (approved
direction). Open it in a browser; toggle theme top-right, `j`/`k` to move, `y`/`x`/`s` to
keep/drop/snooze.

## 9. Decisions & v1 scope

**Settled decisions:**

| Area | Decision |
|---|----------|
| Model | One `Album` table with a state field (`suggested→saved→wanted→acquiring→owned`/`dismissed`) — not two tables. |
| Reconcile | **Beets CLI** behind a config-driven seam (command + config path), not direct SQLite (raw SQLite locked constantly). One `beet list -a -f '$mb_releasegroupid'` dump → in-memory diff (§5). |
| Identity | MusicBrainz release-group as the spine; 3-tier resolution (barcode → ISRC-cluster → fuzzy). Resolve once at ingest, store the id; reconcile is a deterministic join thereafter (§5). |
| LLM matching | **Not building it** — the D0 spike showed the unresolved tail is MB-absent, not fuzzy-matchable, so an LLM can't help. Tail handled by manual-match + re-resolve instead (§5, §5a, ROADMAP D17). |
| Play history | Poll `recently-played` from install; **no** GDPR backfill (accept cold-start, §4a/§6a). |
| 6a thresholds | listened = ≥4 tracks or ≥3 days; forgotten = ≥21 days & <2 plays. Config-tunable. |
| 6b seed set | Union of kept-album artists **and** followed artists. (Not in v1.) |
| Spotify auth | Authorization Code (+ client secret). Refresh tokens now expire at **6 months** → web re-auth flow + proactive warning are **v1-critical**; store `spotify_authorized_at` (§8c). |
| Redirect URI | Config-driven public HTTPS callback, registered per-deployment in the Spotify dashboard; loopback `127.0.0.1` (not `localhost`) for local dev (§8c). |
| Stack | FastAPI + SQLAlchemy 2.0/Alembic + httpx (thin Spotify adapter) + APScheduler + uv; React + TS + Vite + TanStack Query; single Docker image. Full table in §15. |
| UI model | A **set of worklists** in funnel order — Releases (§6b) / Decide / Acquire / Import — over the state lifecycle, plus browse + a Spotify-status banner (§8d). Releases and Import are post-v1. |
| UI aesthetic | **Sharp, dense, quiet** — square corners, flat (1px rules, no shadows), near-monochrome + one accent, sans-for-text/mono-for-data, keyboard-first. Theme-aware (both), ~48px thumbnails, no CSS framework, design tokens (§8e). |
| State machine | `suggested → saved → wanted → acquiring → owned` (+ `dismissed`). Entry state by provenance: Spotify saves enter at `saved`, 6b/6c discoveries at `suggested`. `owned` derived by reconcile from `wanted`/`acquiring`; `dismissed` reachable from `suggested` (rejected suggestion) or `saved`/`wanted` (verdict drop), disambiguated by provenance (§4). |
| Storage | **PostgreSQL**, connection from config (host/port/db/user/pass). No local SQLite of its own. |
| Cover art | **Owned/retained blobs in Postgres**, in a dedicated `album_art` table (splittable to its own schema/DB later). Self-served (`/art/<album-id>`) with ETag/immutable caching; a front cache only if slow. Not hotlinked. Sourced from Spotify / Cover Art Archive / beets (§4b). |
| Deployment | **Agnostic** — app only requires a Postgres backend + a beets command, both from config (§8a). My blink+partridge hosting is a reference deployment (§8b), not a requirement. |
| Acquisition | Manual; assisted by one-click Bandcamp search-URL per want (§7). Links, never buys. |
| Testing | Ports-and-adapters + pure core + injectable clock + configurable base URLs → unit-test the bulk; real-Postgres integration (testcontainers); Docker E2E (app+postgres, fake-Spotify stub) for the full flow (§14). |
| Observability | `GET /metrics` (Prometheus), DB-sourced so it's correct across the API/worker split; alerts for reauth-due and stalled pollers via Grafana (§16, ROADMAP D18). |

**v1 scope (the "thin" cut):**
Spotify OAuth **with a working re-auth flow** (§8c) → saves ingest → reconcile against
beets → web list of *saved-but-not-owned*, each with a Buy-on-Bandcamp link **and a
manual "link to library / mark owned"** (so edition-mismatch and MB-absent albums can
always reach `owned`, §5) → the **6a verdict prompt** (leaning on the time-based
"forgotten" trigger early, per the cold-start note). Play-history polling ships in v1
because 6a's "listened" trigger depends on it, even though it starts quiet.

**Explicitly deferred to v2+:** 6b new-release watch, 6c catalogue backfill,
notifications, GDPR history backfill, any Bandcamp scraping beyond the search URL.
*Not* deferrable: the Spotify re-auth flow — the 6-month token expiry (§8c) makes it
core, or the whole thing silently dies within 6 months.

## 9a. Suggested build order (for the eventual plan)

1. **Skeleton + environment contract** — Python service reading config for its Postgres
   connection + beets command (§8a); schema/migrations for `album` + `play_history`;
   a startup healthcheck that proves it can reach both Postgres and beets. Deployment
   (compose/host wiring) is separate and swappable — the reference setup is §8b.
2. **Spotify auth (incl. re-auth) + saves ingest** — httpx-adapter Authorization Code flow
   (§15); registered redirect URI; token + `spotify_authorized_at` persistence; the
   `invalid_grant` → pause-jobs → "Reconnect Spotify" web flow (§8c). Then poll saved
   albums → `album` rows in `saved` state. Do the re-auth handling here, not later — it's
   cheap once the OAuth flow exists and it's the difference between "works" and "dies in
   6 months".
3. **Reconcile** — ISRC→MB→release-group resolution + the `beet list` dump-and-diff;
   derive `owned`. The riskiest/most valuable piece (§5) — validate matching quality
   early (a standalone spike against real saved albums is worth it before wiring it in).
4. **Web list + Bandcamp links** — SPA view of saved-but-not-owned with buy buttons.
   At this point the core loop already closes.
5. **Play-history polling** — `recently-played` job → `play_history`.
6. **6a verdict prompt** — triggers + keep/drop UI + state transitions.
7. *(v2)* 6b, 6c, notifications.

## 10. What to salvage from the old repos

- `spotify-scripts`: the **album + ResourceUri + match-graph data model** is sound;
  the **fuzzy matcher is not** (replace per §5). `artistwatch.py`'s new-release logic
  is directly reusable for nudge **6b** (just re-seed it off kept albums, not followed
  artists). Its `ArtworkTask` (download Spotify album art) is directly reusable for §4b —
  just write to the `album_art` table instead of an images dir. The custom SQLite job
  queue is probably more than a personal tool needs —
  reconsider. Ignore `wander.py` / `trackclustering.py` — dead endpoints and out of
  scope now that there's no recommender.
  - **Anti-pattern to avoid:** it read the beets SQLite db directly with raw concurrent
    connections and **locked constantly**. Hence §5's beets-CLI decision and §8's
    Postgres-for-own-state decision — no raw SQLite contention anywhere.
  - **Dead assumption:** it relied on a *permanent* Spotify refresh token. Spotify now
    expires them at 6 months (§8c), so the headless-forever model is gone — a web re-auth
    flow is mandatory.
- `record-library`: the **inbox → beets import** workflow is clean and worth keeping as
  the "land" step. This is where acquired files enter and trigger reconcile.

## 11. Reconcile / identity spike (do before building around §5)

> **Done — verdict GO.** 80-album real sample: 86% resolved (barcode-first carries 56%),
> 98% beets coverage, owned matches correct; the 14% tail is MB-absent, not a matching
> weakness → LLM Tier-3 dropped, tail handled per §5. Tooling + full write-up:
> [`spikes/reconcile/`](spikes/reconcile/) (`RESULTS.md`).

**Why:** the Spotify→MusicBrainz→beets match is the single technical risk — it's what
made the old system only "sort of work." A want-list that mis-judges ownership is
actively harmful (a **false positive** hides an album from the list forever → the exact
failure the tool exists to prevent). The spike **measures the match rate and failure
modes on real data** before the architecture commits to this chain. It also **gates the
§5a LLM decision** (how big is the fuzzy tail, really?).

**Standalone & decoupled:** read-only Spotify + MusicBrainz API calls + a read-only
`beet list`. No Postgres, no blink, no compose — can run anytime, including before the
blink→nix conversion.

**Design:**
- **Input:** a deliberately *mixed* sample of ~50–100 saved albums — old/new,
  mainstream/obscure, various formats & labels. (A uniform easy sample flatters the
  result and teaches nothing about the tail.)
- **Per album:** run all three tiers (§5); record which tier resolved it (or none), the
  Tier-2 confidence (how many ISRCs agreed), the resolved release-group id, and
  owned/not-owned against the beets dump.
- **Also dump beets and measure** what fraction of *owned* albums even carry a
  `mb_releasegroupid`. This is the accuracy ceiling regardless of the Spotify side.
- **Metrics (make it a decision, not a vibe):**
  - resolution rate, broken down by tier (Tier-3-heavy = yellow flag);
  - **ownership accuracy**, with special attention to false positives;
  - the "hard bucket" — list unresolved albums; look for patterns (all new? all comps?
    one label?) → tells you if the tail is ignorable or needs a manual-match escape hatch.
- **Ground truth for accuracy:**
  - hand-label ~20 known-owned + ~20 known-not-owned and check verdicts; and/or
  - reverse round-trip: feed beets albums that *have* a release-group id back through the
    pipeline and confirm it marks them owned.
- **Practicalities:** MusicBrainz anon limit ~1 req/s (Tier 2 is 10+ lookups/album, so a
  100-album run is minutes) — cache, and set a proper `User-Agent` (MB blocks otherwise).

**Decision gate:** high accuracy with few false positives → build on this chain. Tier-2
carrying the load → confirms the caching / barcode-first design matters. Fat
unresolvable tail → decide *now* between an LLM Tier-3 (§5a) vs a manual-match UI, in a
script rather than after building the whole tool.

## 12. Extension (post-MVP): Transmission → auto-land pipeline

> **Status: sketch, explicitly not MVP.** This automates the one manual step left in the
> loop (§3): getting downloaded files *into* beets. Today I download to the seedbox by
> hand, then rsync + `beet import` by hand. This closes that gap.

**What it does:** poll Transmission for newly-completed downloads, match each against the
want-list, and offer a one-click **Import** that pulls the files over, runs a beets
import, and tidies the local staging — after which reconcile (§5) flips the want to
`owned` on its own.

**Flow:**
1. **Poll Transmission RPC** (hourly/daily) — `torrent-get` for completed torrents
   (`percentDone == 1`), with name, hash, `downloadDir`, file list. (`transmission-rpc`
   Python lib; note the RPC's `X-Transmission-Session-Id` 409-handshake.)
2. **Diff against a seen-set** in Postgres → only genuinely new completions.
3. **Match torrent → want.** Messy scene naming vs the want-list — the *same* imperfect
   problem as §5, so: fuzzy/LLM-adjudicated **suggestion**, never an automatic action.
   Prime §5a LLM-adjudicator territory; must be allowed to abstain → "no confident match".
4. **Offer an Import button** for every new completion — matched *or not* (see the shared
   no-match rule below). A matched candidate shows the want it satisfies; an unmatched one
   imports as new `owned` with no prior want.
5. **On click, the import task:**
   - **Transfer** the torrent's files off the seedbox — **copy, not move** (see seeding
     rule below): `rsync` over SSH into the beets **inbox**.
   - **Import** via the existing beets CLI seam (§5): `beet import` moves inbox → library
     (the `record-library` `move: yes` workflow, §10).
   - **Tidy** the *local* staging copy afterwards. Nothing on the seedbox is touched.
6. **Reconcile closes the loop** — the new release-group appears in beets, §5 marks the
   want `owned`. The import task itself sets no ownership state.

**Hard rules / design calls:**
- **Import doesn't require a want match** (shared rule, applies to §13 too — see there for
  the rationale). An unmatched completion imports as new `owned`; reconcile back-links it
  if a matching Spotify save ever appears.
- **Never disturb seeding.** Private-tracker ratio depends on continued seeding, so the
  seedbox files and the torrent are **never moved or deleted** — we only ever *copy* off.
  "Tidy up" is strictly the local inbox staging, post-import.
- **Detection is automatic; the import action is human-gated.** Matching is imperfect, so
  a click confirms before any files move or import runs.
- **Post-import sanity check.** beets auto-tagging can match to the *wrong* release. After
  import, verify the imported release-group matches the want's; if not, flag it rather
  than let reconcile silently mark a mismatch as owned.
- **Idempotent + recoverable.** Track per-torrent import state (matched / importing /
  done / failed) so a torrent is never imported twice and transfer/import failures can
  retry. Mind disk space in the inbox.
- **Reuses existing seams:** beets CLI (import), reconcile (owned-marking), the want-list.
  Little new surface beyond Transmission + file transfer.

**Config additions (extends the §8a contract):**
| Requirement | Config |
|---|---|
| Transmission RPC | rpc url, username, password |
| Seedbox file transfer | SSH host/port/user/key, remote download base path, local inbox path (or: an sshfs/NFS mount, in which case transfer is a local copy and no per-import SSH is needed) |
| Import behaviour | beets import flags / non-interactive mode (reuses the §5 beets command) |

**Access note (answering "needs SSH too?"):** yes — Transmission RPC gives *control and
metadata only*, not file bytes. File retrieval is a separate channel: rsync-over-SSH, or
a pre-existing seedbox mount. Two distinct credentials (RPC + SSH), both config-driven.

**Safety:** this feature *downloads files and runs imports* — both gated behind an
explicit user click, and all credentials come from config, never from torrent names or
any other observed content.

**Open questions:**
- Match reliability, and whether to *require* a confirmed MB-tag before enabling Import.
- beets non-interactive import mode + autotag confidence threshold (quiet vs. review).
- Multi-album / non-music / mixed torrents; how to handle partial matches.
- A sibling watch-dir importer for non-torrent acquisitions (Bandcamp zips) reuses this
  extension's match→import→tidy tail — see §13.

## 13. Extension (post-MVP): watch-dir import (Bandcamp zips & dropped folders)

> **Status: sketch, not MVP.** Sibling of §12 — it **reuses the same match → Import
> button → beets import → tidy → reconcile tail**, and differs only at the front: the
> files are already local and *owned*, so instead of a Transmission poll + SSH transfer
> there's a directory watch + unpack. Makes landing a Bandcamp purchase as easy as
> dropping the zip in a folder.

**Motivation:** the §7 acquisition assist points me at Bandcamp; purchases arrive as
zips. This closes the loop on them with zero ceremony.

**Flow (only the front differs from §12):**
1. **Watch a configured directory.** A periodic **scan** is the default (simple, and works
   over network mounts where inotify may not fire), with a **settle check** (file size
   stable / not still being written) so partial downloads aren't grabbed mid-copy.
   inotify/watchdog is an optional optimisation.
2. **New item → diff against a processed-set** in Postgres (by path + content hash) for
   idempotency, so re-scans don't reprocess.
3. **Unpack.** Extract the zip to a staging dir; loose folders dropped in are taken as-is.
   **Guard against zip-slip / path traversal** on extraction.
4. **Match to the want-list** — same imperfect problem, human-gated suggestion as §12,
   **but with a better signal: read the embedded audio tags** (Bandcamp FLACs usually
   carry proper artist/album, sometimes even MB ids) rather than relying on the filename.
5. **Offer Import → beets import → reconcile flips owned.** Identical to §12 from here.
6. **Tidy:** clean the extraction staging, and dispose of the original zip per config.

**Differences from §12 (why it's simpler):**
- **No Transmission, no SSH, no seeding constraint.** Files are already local.
- **Adds an unzip/extract step** where §12 has a transfer step.
- **The zip is yours** → safe to move or delete after import. Config: **archive to a
  `done/` subdir (default, safest) / delete / leave in place.** (Deliberate contrast with
  §12's copy-never-move-never-delete seedbox rule.)
- **Matching is more reliable** — real tags beat scene names.

**Config additions (extends §8a):**
| Requirement | Config |
|---|---|
| Watch directory | path to watch; staging/extract path |
| Post-import disposition | archive dir / delete / leave (default: archive) |
| Import behaviour | reuses the §5 beets command + §12 import settings |

**DECIDED — imports don't require a want match (shared by §12 and §13).** Acquisitions
often bypass the want-list entirely — a Bandcamp buy you found directly, or a torrent you
grabbed on a whim. So the shared import tail **allows importing with no matching want**:
it simply becomes `owned` in beets, and if a matching Spotify save ever appears later,
reconcile (§5) back-links them. Don't force everything through the want-list. This is a
property of the common tail, so it holds for both the Transmission (§12) and watch-dir
(§13) fronts.

**Safety:** extraction guards against path traversal; import stays human-gated;
filenames and tags are treated as data, never as instructions.

**Open questions:**
- Accept formats beyond `.zip`? (Bandcamp offers zip; folders are handled; other archive
  types are easy to add but out of initial scope.)
- Auto-import vs. confirm for *confidently-tagged* drops — since embedded tags make
  matching strong, a high-confidence drop could skip the button. Probably still confirm
  in v1 of the extension; revisit once match quality is known.

## 14. Testing strategy

Goal: **unit-test as much as possible**, plus a small number of high-value **E2E** tests
that run the real app + Postgres in Docker with external services stubbed. How much is
unit-testable is decided by architecture, so the design-for-testability rules below are
load-bearing, not optional.

### Design for testability (bake in from day one)
- **Ports & adapters.** Spotify, MusicBrainz, Cover Art Archive, beets, Postgres,
  Transmission, SSH, **and the clock** all sit behind interfaces; the core logic (state
  machine, 6a triggers, reconcile matching, dedupe, 6b diff) is **pure functions/services
  over data**. → the bulk is unit-testable with *no mocks*, and edges are swappable for E2E.
- **Configurable base URLs** for Spotify/MB/CAA (already config, §8a) — so E2E redirects
  them to a local stub. **Don't hardwire `api.spotify.com`.**
- **Injectable clock.** 6a triggers and the reauth countdown are time-based — they take an
  injected `now`, never the system clock, so tests are deterministic.

### Unit tests (the bulk) — pure logic, table-driven
- state-machine transitions incl. skip/reverse/`dismissed` edges;
- 6a triggers (listened/forgotten) over fabricated play-history + injected clock + thresholds;
- reconcile matching: ISRC clustering, release-group selection, owned-set diff (over fixtures);
- dedupe (release-group / Spotify id), 6b new-vs-seen diff;
- Bandcamp URL builder, art-source selection;
- adapter **parsers**: map recorded Spotify/MB/CAA responses and `beet list` output to our
  models (feed captured payloads, assert mapping) — no network.

### Integration tests (middle)
- **Repositories against a real Postgres** (testcontainers): run migrations, exercise repo
  methods, assert. Don't mock the DB — SQL + migrations are where the bugs are.
- **beets adapter against a tiny seeded `library.db` fixture** (a couple of albums with
  `mb_releasegroupid`) so the CLI query + parse survive real `beet` output. Fixture
  harness already built: [`fixtures/beets/`](fixtures/beets/) (silent tagged FLACs →
  `beet import` → `library.db` + owned dump, reproducible via Docker).

### E2E (few, high-value)
- **docker compose: app + postgres**, plus a **fake-Spotify HTTP stub** serving
  `/me/albums`, `/albums/{id}`, recently-played, following, and the **OAuth token
  endpoint**; the app hits it via the configurable base URL. MB/CAA stubbed or recorded.
  beets shipped as a **seeded fixture `library.db`** in the app container.
- Drive the full flow, assert end to end: OAuth → ingest saves → reconcile → one album
  resolves **`owned`** (it's in the beets fixture), another stays `wanted`/`saved`;
  worklists/API reflect it. Include the **re-auth path** (stub returns `invalid_grant` →
  app flags reconnect, pauses jobs).
- Prefer a **real stub server** over monkeypatching the client, so E2E exercises the real
  HTTP + parsing layers, not just the happy-path mapping.
- **As built (D9):** a pytest E2E runs the real app (via TestClient) + real Postgres
  (testcontainers) + real bundled beets, with Spotify + MusicBrainz served by a **live
  stub** over the configurable base URLs — the whole loop incl. re-auth. Chosen over a
  docker-compose harness: same real chain end-to-end, far less orchestration; a compose
  file lands with the D10 deploy where it's needed anyway.

### Frontend
- Component/unit (Vitest + Testing Library): the shared album-row, worklist rendering,
  keyboard triage (`j`/`k`/`y`/`x`/`s`).
- Optional but recommended: a **Playwright** browser-E2E driving the real SPA against the
  dockerized backend + fake Spotify — the triage UX end to end.

### Extensions
- Transmission (§12): stub the RPC + a local dir standing in for the seedbox; assert
  detect → match → import → reconcile → `owned`, **and the seeding-safety rule** (seedbox
  originals untouched — copy never move/delete).
- watch-dir (§13): drop a fixture zip in the watched dir; assert unpack → match → import →
  `owned`, plus the **no-match import** path.

### CI & stack
- **Unit + integration on every push** (fast; testcontainers Postgres). **E2E (compose) as
  a separate job.** GitHub Actions (repo is on GitHub).
- Suggested stack: **pytest + testcontainers + httpx + respx/VCR** (backend); **Vitest +
  Testing Library + Playwright** (frontend). Track coverage, but treat % as a guide, not a
  gate — prioritise the **state machine, 6a triggers, and reconcile** (the correctness-
  critical, false-positive-prone core; cf. the §11 spike, which validates matching on real
  data while these tests lock the logic).

## 15. Tech stack

Concrete choices. External systems stay behind ports (§14), so any of these is swappable
without touching the core.

### Backend (Python)
| Concern | Choice | Notes |
|---|---|---|
| Runtime | **Python 3.12+** | |
| Web framework | **FastAPI** + **Pydantic v2** | async; OpenAPI schema → typed frontend client |
| Config | **pydantic-settings** | env-var driven, matches the §8a contract |
| HTTP client | **httpx** (async) | + **respx** in tests |
| Spotify | **thin httpx adapter** (own code) | configurable base URL for E2E stubs (§14); full control of the 6-month re-auth (§8c). Not tekore. |
| MusicBrainz / Cover Art Archive | httpx, configurable base URL | rate-limit + `User-Agent` handled in the adapter (§11) |
| beets | subprocess over the `beet` CLI seam (§5) | command + config path from config |
| DB | **PostgreSQL** via **SQLAlchemy 2.0** (typed) + **psycopg3** | |
| Migrations | **Alembic** | migrations are tested (§14) |
| Scheduler | **APScheduler** in-process | jobs *also* exposed as CLI commands → cron-able + unit-testable; not tied to a host scheduler |
| Packaging | **uv** + lockfile | |
| Quality | **Ruff** (lint+format) + **mypy** | |

**Why Python, not Go (considered).** Go was weighed — it would consolidate with `blink`
and nix-package more cleanly as a single static binary. But the two reasons Python was
*originally* obvious have gone (we use the beets **CLI** not its library, §5; the
clustering/data-science work is dead), so this was decided on merits, not inertia: the
tool orbits beets (which must be in the runtime regardless — Python lets app + beets share
one image with no sidecar), and the reconcile fuzzy tail (`rapidfuzz`), §13 tag-reading
(`mutagen`/`mediafile`), a possible §5a LLM step, and spotify-scripts salvage all sit in
Python's sweet spot. Performance is irrelevant at single-user, I/O-bound scale, and
homelab-language consolidation was explicitly not a priority. External systems stay behind
ports (§14), so this isn't a one-way door.

### Frontend
| Concern | Choice | Notes |
|---|---|---|
| Framework | **React** + **TypeScript** | best fit for the testing/codegen tooling |
| Build | **Vite** | pairs with Vitest |
| Styling | hand-rolled **CSS / CSS-modules** + design tokens | §8e aesthetic; no CSS framework |
| Server state | **TanStack Query** | caching/refetch for the worklists |
| API client | **generated from FastAPI's OpenAPI** (e.g. openapi-typescript) | front/back types stay in sync |
| Tests | **Vitest + Testing Library**; Playwright (optional) | §14 |

### Packaging & deploy
- **Single multi-stage Docker image**: Node stage builds the SPA → Python runtime serves
  the JSON API *and* the built static assets; **beets is a bundled dependency** in the
  image, and the beets **library is mounted** in (resolved in §5). Behind Traefik on the
  `blink` stack (§8b).
- **Monorepo**: `backend/` + `frontend/` in this repo; one image out.

## 16. Observability & metrics

The app runs unattended on a schedule, so its main operational risk is **silent failure**:
a poller dies or the Spotify refresh token expires and nothing tells me until I next look
and find the library hasn't grown. Prometheus metrics + Grafana alerts close that gap
(Grafana/Prometheus already run on partridge, §8b). Built in ROADMAP **D18**.

- **`GET /metrics`** in Prometheus text format, served by the API.
- **Sourced from the DB, not in-process counters.** The API and the poller `worker` are
  separate processes (§15), so worker-local counters are invisible to the API's `/metrics`.
  Instead, pollers persist a **heartbeat** (last-run, last-success, last-error) to a small
  `job_run` table each pass, and `/metrics` derives everything by querying the DB. One
  scrape target, correct across processes, survives restarts.
- **Metrics that matter:**
  - `wantlist_spotify_connected`, `wantlist_spotify_reauth_days_remaining` — alert *before*
    the 6-month expiry (§8c) rather than discovering it after ingest has silently stopped.
  - `wantlist_albums{state=…}` — the funnel as gauges (Decide/Acquire backlog);
    `wantlist_albums_missing_art`.
  - `wantlist_job_last_success_timestamp{job=…}` + run/error counters — alert if any poller
    (saves, play-history, watch, reconcile) stalls or errors.
- **Boundary:** the app *exposes* metrics; the Prometheus scrape config and Grafana
  dashboards/alerts live in the `house`/`lab` repos, per the deployment split (§8b).
