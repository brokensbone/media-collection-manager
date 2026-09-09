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
