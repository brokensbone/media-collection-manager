# wantlist

A smart want-list over Spotify + beets — captures what you want to own, tells you whether
you already own it, and nudges you to curate and acquire. See [SPEC.md](SPEC.md) for the
design and [ROADMAP.md](ROADMAP.md) for the sequential deliverables.

## Layout

- `backend/` — FastAPI service (Python 3.12, uv). Ports/adapters with a pure core (§14).
- `frontend/` — React + TypeScript SPA (Vite).
- `fixtures/beets/` — reproducible seeded beets library for tests.
- `spikes/` — throwaway spikes (D0 reconcile).

## Dev

Backend (from `backend/`):
```
uv sync
uv run pytest        # tests
uv run ruff check .  # lint
uv run ruff format . # format
uv run mypy          # types
uv run uvicorn wantlist.app:app --reload   # run the API
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
