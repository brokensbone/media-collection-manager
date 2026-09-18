# Media Collection Manager

Media Collection Manager is a self-hosted music want-list: it tracks albums you save,
compares them with a beets library, and provides queues for deciding, acquiring, and
importing records.

The application is intended for a private, single-user deployment. It has no built-in
authentication or authorisation; put it behind an appropriate access-control layer before
making an instance reachable by anyone else.

## Nix

The flake is the supported upstream packaging interface. It exposes these packages:

- `mcm-api` — serves the API and bundled SPA. It listens on 127.0.0.1:8000 by default;
  set `MCM_HOST` and `MCM_PORT` to override that.
- `mcm-worker` — runs scheduled polling and import work.
- `mcm-migrate` — runs Alembic, e.g. `mcm-migrate upgrade head`.
- `frontend` and `backend` — separately consumable build outputs.
- `image` — an OCI image whose default command is `mcm-api`.

`mcm-api` supplies the packaged SPA through `MCM_STATIC_DIR` unless the deployment
sets that variable itself. Runtime configuration remains environment-based; see
[`deploy/local/.env.example`](deploy/local/.env.example) for the available settings. A host
integration should run migrations before the API and worker, and manage all credentials outside
the Nix store.

## Layout

- `backend/` — FastAPI service (Python 3.12, uv). Ports/adapters with a pure core (§14).
- `frontend/` — React + TypeScript SPA (Vite).
- `fixtures/beets/` — reproducible seeded beets library for tests.
- `spikes/` — throwaway spikes (D0 reconcile).

## Matching downloads to albums

A finished download arrives named something like
`Sasha - Fabric 99 [FLAC] {fabric}`, and MCM has to say which album that is.
Comparing strings gets the near-misses wrong in a way no amount of tuning fixes:
`Fabric 99` and `Fabric 19` differ by one character but are different records,
while `Portishead (2008) Third [Mercury; B0011141-02]` and `Portishead — Third`
differ by most of their characters and are the same one.

So the two halves are split. `domain.match.retrieve` is deliberately loose and only
has to get the right album *somewhere* into a shortlist — measured at 98% recall in
twelve. Choosing one of them, or saying none, is a `ports.album_judge.AlbumJudge`,
implemented against TypeSafe in `adapters.typesafe_judge`.

Set `MCM_TYPESAFE_API_KEY` to enable it. Without a key the old string matcher still
runs, and it is also the fallback if the API is unreachable, so detection never loses
a download. A verdict below `MCM_MATCH_MIN_CONFIDENCE` is treated as no match and
lands in the same tail as anything unrecognised, to be hand-imported.

Matching otherwise happens once, when a download is first detected, so anything that
arrived before its album was saved stays unmatched for good. `POST /imports/rematch`
puts the Import worklist back through it — which is also how an improved matcher
reaches what an older one decided. It redoes every music download still awaiting a
decision, so a wrong match is corrected or cleared as well as a blank filled; rows
already acted on are untouched. It is bounded, because each download is a judgement
call and the whole worklist would outlive the gateway timeout, so walk it by adding
`considered` to `offset` while `remaining` is above zero:

```
curl -XPOST 'http://127.0.0.1:8000/imports/rematch?limit=50&offset=0'
```

## Resolving albums to MusicBrainz

Every album needs a MusicBrainz release-group id before ownership can be reconciled.
Barcode lookup settles most of them exactly. The text tier behind it has the same
shape as the matching above, and the same problem: Spotify joins every credited
artist with commas, so quoting the whole credit asks MusicBrainz for an artist that
does not exist there. `Alva Noto, Ryuichi Sakamoto` finds nothing, though the album
is present — credited `Alva Noto, 坂本龍一`.

Searching the leading artist alone finds it, and also finds unrelated records:
`Becker & Mukai — Spirit Only` returns a Margaret Becker hymnal at score 100. So the
wider search and the judgement are a pair, and neither is safe alone. With
`MCM_TYPESAFE_API_KEY` set, the text tier widens and a judgement picks; without one
it keeps the narrow search and the score gate, unchanged.

One thing worth knowing if you tune it. These candidate lists are short — often a
single release group against "none of these" — so `MCM_RESOLUTION_MIN_PROBABILITY`
gates on the probability of the answer, not on confidence. Confidence measures how
concentrated a distribution is, and an exact artist-and-title match against one
alternative splits 0.76/0.24: a clear answer and an unconcentrated distribution at
the same time.

## Dev

Backend (from `backend/`):
```
uv sync
uv run pytest        # tests
uv run ruff check .  # lint
uv run ruff format . # format
uv run mypy          # types
uv run uvicorn mcm.app:app --reload   # run the API
```

Frontend (from `frontend/`):
```
npm install
npm test         # tests
npm run lint     # biome
npm run typecheck
npm run dev      # dev server
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push and PR.
