# Roadmap — sequential deliverables

Derived from [SPEC.md](SPEC.md). Each deliverable is a **green-light unit**: say "go
ahead", it gets built, then it's checked against its **Done when** gate before the next
starts. Section references (§) point into the spec.

Phases: **P0** foundations (pre-MVP) · **P1** MVP core loop · **P2** live · **P3** post-MVP
increments. The MVP boundary is after **D9**.

Guiding rule from the spec: **the reconcile spike (D0) comes first** — it needs no infra
and de-risks the one hard part before anything is built around it.

---

## P0 — De-risk & foundations

### D0 · Reconcile / identity spike  *(§11, standalone)*  — ✅ done: **GO**
Prove the Spotify→MusicBrainz→beets match on real data before committing the architecture.
Ran on an 80-album real sample: **86% resolved** (barcode-first carries 56%), **98% beets
coverage**, owned matches correct. The 14% tail is **MB-absent / not-real-albums, not a
matching weakness** → **D16 (LLM Tier-3) dropped**; handle the tail with manual-match +
periodic re-resolve, keeping unresolved albums as first-class wants (§5). Full write-up:
[`spikes/reconcile/RESULTS.md`](spikes/reconcile/RESULTS.md). Tooling: [`spikes/reconcile/`](spikes/reconcile/);
fixture: [`fixtures/beets/`](fixtures/beets/).
- Standalone script: read-only Spotify + MB/CAA + `beet list` over a mixed ~50–100 album sample.
- Measure resolution rate by tier, ownership accuracy (esp. false positives), the unresolved "hard bucket", and how many owned albums even carry an `mb_releasegroupid`.
- **Done when:** a written result gives a go/no-go on the ISRC→MB→release-group chain, and answers whether an LLM Tier-3 (§5a) is needed (fat tail?) or the tail can go to a manual inbox.

### D1 · Repo scaffold + CI
Monorepo shell and the test/quality harness that everything else rides on.
- `backend/` (uv, FastAPI skeleton, Ruff, mypy, pytest) + `frontend/` (Vite, React, TS, Vitest); ports/adapters package layout; pydantic-settings config.
- GitHub Actions running lint + typecheck + both (trivial) test suites.
- **Done when:** `uv run pytest` and `vitest` both run green, lint + typecheck pass, and CI is green on push. *("test suite runs")*

### D2 · Service skeleton + DB migrations + health  — ✅ done (pending CI)
The app boots and can reach its two dependencies, with schema in place.
- Alembic migrations create `album`, `play_history`, `album_art`, auth/token tables (§4).
- Startup/health endpoint verifies Postgres connectivity and that the `beet` command runs.
- Integration test against a **testcontainers Postgres** (migrations apply cleanly).
- **Done when:** `GET /health` reports OK incl. Postgres + beets reachability; migrations apply on a fresh Postgres in CI. *("boots, reaches Postgres and beets")*

---

## P1 — MVP core loop

### D3 · Spotify auth + re-auth  *(§8c, §15)*  — ✅ done (pending CI)
The thin httpx adapter and the whole OAuth lifecycle, including the 6-month reconnect.
- Auth-code flow (client secret), token + `spotify_authorized_at` persistence, refresh, `invalid_grant` → pause-jobs → reconnect; configurable base URL; fake-Spotify stub for tests.
- Minimal web "Connect / Reconnect Spotify" + status (reauth countdown).
- **Done when:** OAuth completes against real Spotify *and* the stub; refresh works; `invalid_grant` surfaces reconnect; status shows connected + days-to-reauth. *("can connect to Spotify, and reconnect")*

### D4 · Saves ingest + dedupe + art  *(§4, §4b)*  — ✅ done (pending CI)
Pull the firehose in, once each, with covers.
- Poll saved albums → `album` rows in `saved`; dedupe by release-group / Spotify id; record provenance. APScheduler job + a CLI command form.
- Async art fetch → `album_art` blob; served at `/art/<id>` with ETag.
- **Done when:** an ingest run populates albums (stub + real) with **no duplicates on re-run**; covers serve; unit + integration tests pass. *("saved albums appear, idempotent")*

### D5 · Reconcile engine + Owned/Library view  *(§5)*  — ✅ done (pending CI)
The risky core, now wired in — plus the first real read-only screen.
- ISRC→MB→release-group resolution (resolve-once, store the id); `beet list -a -f '$mb_releasegroupid'` dump → in-memory diff → derive `owned`. MB/CAA adapters (configurable base URL, rate-limit, User-Agent).
- A read-only Library / Owned view so results are visible.
- Ownership link carries a **source** (`auto` from reconcile vs `manual` sticky link, §4) — reconcile computes auto-ownership and never clobbers a manual link. (The manual *action* is D7; this deliverable just makes the model respect one.)
- **Done when:** against saved albums + a seeded beets fixture, reconcile marks the owned ones `owned` and leaves the rest — matching D0's approach; a manual link is respected and survives a reconcile pass; matching logic unit-tested; integration test hits the beets fixture; accuracy on the fixture recorded. *("ownership derived correctly against beets")*

### D6 · Verdict + Decide worklist  *(§6a, §8d)*  — ✅ done (pending CI)
The curation gate — shipping first with the time-based trigger that works from day one.
- State transitions `saved → wanted` / `dismissed`, plus Snooze; the **"forgotten"** trigger (saved ≥ T days, ~no plays). Decide worklist UI in the §8e aesthetic (per the [mockup](mockups/decide-worklist.html)); keyboard triage.
- **Done when:** stale saves surface in Decide with the right "why"; keep→`wanted`, drop→`dismissed`, snooze all work via UI + API; state-machine unit tests pass. *("can triage saved → wanted/dismissed")*

### D7 · Acquire worklist + Bandcamp + `acquiring` + mark-owned  *(§7, §8d)*  — ✅ done (pending CI)
Close the loop's manual middle with buy-assist — and make it always closable.
- Acquire worklist over `wanted`; one-click Buy-on-Bandcamp search URL; **Mark as ordered** → `acquiring` (drops out of the queue; cancel restores); reconcile promotes `acquiring`/`wanted` → `owned`.
- **Mark owned** (minimal manual resolve, §4/§5): a sticky `manual` link → `owned` that reconcile never clobbers. This is what lets edition-mismatch and MB-absent albums leave the buy list; MVP. *(Picking a specific beets album to link — the assisted search/suggestions — is D17; fallback/paste-a-URL buy links likewise deferred as YAGNI for now.)*
- **Done when:** wanted albums show working buy links; mark-ordered → `acquiring`; when a matching album lands in beets, reconcile flips it `owned`; **a mark-owned want (edition mismatch or MB-absent) reaches `owned` and stays there across reconcile**; tests pass. *("wanted → owned with buy assist, always closable")*

### D8 · Play-history + "listened" trigger  *(§4a, §6a)*  — ✅ done (pending CI)
Upgrade the verdict from a timer to "you've actually heard this."
- Poll `recently-played` → `play_history` (scheduled + CLI); add the **"listened"** trigger to Decide (≥N tracks / ≥M days), clock injected.
- **Done when:** plays accumulate; an album with enough plays surfaces in Decide via the listened trigger; trigger unit tests pass with an injected clock. *("listened trigger fires from real play data")*

### D9 · Dashboard + browse + Spotify banner + full E2E  → ✅ **MVP COMPLETE** (pending CI)  *(§8d, §14)*
Everything that makes it a coherent app, and the end-to-end proof.
- Dashboard with per-worklist counts; Library / Owned / Dismissed browse views (via `/albums?state=`); persistent Spotify status banner; a light §8e stylesheet (design tokens, sharp/dense).
- **Full-stack E2E** (§14): the real app + real Postgres (testcontainers) + real bundled beets, with Spotify + MusicBrainz served by a **live stub over the configurable base URLs**, driving OAuth → ingest → reconcile → verdict → acquire + the re-auth path. Implemented as a pytest E2E rather than docker-compose (same real chain, no orchestration overhead; a compose file arrives with D10 deploy anyway).
- **Done:** E2E green (70 backend + 10 frontend tests); all v1 worklists function; the core loop (saved → owned, with curation + buy assist) closes end-to-end. *("full flow E2E green")*

---

## P2 — Live

### D10 · Deploy to blink + Postgres on partridge  *(§8b)*
Make it real. (Independent of dev — can land as soon as the blink→nix conversion is ready; nothing above is blocked on it.)
- Multi-stage image; compose service on blink behind Traefik/TLS; dedicated DB + writer role on partridge; register the Spotify redirect URI; point at the real beets library.
- **Done when:** the app is reachable at its real URL, connected to real Spotify + real beets, and the first real wants are flowing through the worklists. *("running for real")*

---

## P3 — Post-MVP increments

### D11 · Releases worklist + artist-watch + Spotify writes  *(§6b)*  — ✅ done (pending CI)
- `suggested` state; artist-watch seeded from kept + followed artists; Releases worklist with **Save** / **Want** / **Dismiss**; first Spotify **writes** (`PUT /me/albums`, `user-library-modify`).
- **Done when:** new releases from watched artists appear as `suggested`; Save writes to Spotify and enters the flow; Want → `wanted`; dedupe holds; tests pass. *("new releases surface; Save/Want work")*

### D12 · Artist-watch baseline (supersedes §6c backfill)  *(§6b)*  — ✅ done (pending CI)
Reframed after review: D11's watch surfaced full catalogues (a flood), and back-catalogue
surfacing turned out to be unwanted. So D12 corrects the watch to **baseline-then-new**:
- An artist's first watch records its whole catalogue in a `seen_release` ledger and
  surfaces **nothing**; later runs surface only album ids not seen before (genuinely new).
- §6c (push the back-catalogue on keep) is **dropped** — old releases are noise; only new
  ones should surface.
- **Done:** first watch of an artist surfaces nothing (baselines); a subsequent genuinely-new
  release surfaces as `suggested`; already-tracked albums are never re-surfaced. *("only new, never history")*

### D13 · Notifications  *(§8d)*  — ✅ done (pending CI)
- Push/Slack on: a want auto-resolving to `owned`, N items waiting to triage, and re-auth approaching.
- **Done when:** a notification fires on each chosen trigger. *("gets pinged")*

### D14 · Transmission auto-land  *(§12)*  — ✅ done (pending CI)
- RPC poll (409-handshake) → fuzzy match → Import worklist → **rsync-over-SSH** off the seedbox → `beet import -q` → tidy staging; seeding never disturbed.
- **Built lean:** transfer is rsync-over-SSH behind a `FileTransfer` seam (`RsyncTransfer`), copy-only (`--files-from`, never `--remove-source-files`/`--delete`) so seeding is safe; match is `difflib` fuzzy (no LLM, per the D16 call); unmatched completions still recorded for hand-import; hash-keyed seen-set; per-download state `detected → imported | failed`.
- **Done when:** a completed torrent is detected, matched, one-click imported, lands in beets, and reconcile flips it `owned` — with seedbox originals untouched; tests incl. the seeding-safety rule and the no-match import path. *("torrent → one-click import → owned, seeding safe")*

### D15 · Watch-dir import  *(§13)*
- Watch a dir → unpack zip → match (embedded tags) → import; no-match import allowed; original archived/deleted per config.
- **Done when:** dropping a fixture zip results in unpack → import → `owned`, and the no-match path works; tests pass. *("drop zip → owned")*

### D16 · LLM Tier-3 adjudicator  *(§5a)*  — ❌ dropped by D0
The D0 spike showed the unresolved tail is **MB-absent / not-real-albums, not
fuzzy-matchable**, so an LLM can't move the number. Superseded by the tail-handling in
D17. Revisit only if edition-disambiguation false positives later prove a distinct problem.

### D17 · Assisted tail handling  *(§5 — replaces D16, post-MVP)*
Make the ~14% tail low-effort. (The *minimal* manual link already ships in D7; this is the
assistance on top.)
- **Fuzzy-suggested link candidates** — when linking a want, match it against the beets
  library so it's one click (fuzzy is safe here; a human confirms).
- **"Possibly already owned?" hint** in Acquire — proactively surface likely edition
  mismatches (same artist + similar title, different/no rgid) so you don't re-buy.
- **Periodic re-resolve** — retry unresolved albums as MB grows; also catches new releases.
- **Done when:** linking a want offers correct candidates without manual search, likely-owned wants are flagged in Acquire, and re-resolve picks up a formerly-missing release once it exists in MB. *("the tail stops being a chore")*

### D18 · Metrics endpoint (Prometheus) + alerting hooks  *(§16, post-MVP)*
The app runs unattended, so without metrics it can **silently stop working** — a poller
dies, or the Spotify refresh token expires — and I won't notice until I look. Expose
Prometheus metrics so Grafana (already on partridge) can alert.
- **`GET /metrics`** (Prometheus text) on the API, sourced from the **DB** so it's correct
  across processes (the API and the poller worker are separate — in-process counters in
  the worker are invisible to the API). Exposes:
  - `wantlist_spotify_connected` (0/1) and `wantlist_spotify_reauth_days_remaining` →
    alert *before* the 6-month token expiry (§8c);
  - `wantlist_albums{state=…}` → Decide / Acquire backlog gauges; `wantlist_albums_missing_art`;
  - `wantlist_job_last_success_timestamp{job=…}` + run/error counters → alert if a poller
    stalls or errors (the "silently stopped" guard). Pollers write a heartbeat to a small
    `job_run` table on each pass; `/metrics` reads it.
- **Done when:** `GET /metrics` returns valid Prometheus text with the above, and scraping
  it can drive Grafana alerts for (a) reauth-due and (b) a stalled poller. (Prometheus
  scrape config + Grafana dashboards/alerts live in the `house`/`lab` repos, not here.)
- **Pull-forward note:** the reauth-days and job-freshness metrics are the highest-value
  and depend only on things that exist by D8 — worth pulling earlier than the tail work if
  you start running it for real (D10) before then.

---

## Critical path & notes
- **D0 → D1 → D2** are foundations; **D3–D9** are the MVP spine and are mostly linear
  (D5 depends on D4; D6 on D5; D7 on D6; D8 enriches D6). D0 is done (GO): it dropped D16
  and added D17 (manual-match + re-resolve) as the tail's handling.
- Dev + CI run entirely on local + testcontainers, so **D10 (deploy) is not on the
  critical path** — pull it forward the moment blink is nix-ready if you'd rather deploy a
  walking skeleton early.
- Every deliverable lands with its tests (§14) — "done" always includes green tests, not
  just working code.
