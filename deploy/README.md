# Local deploy (disposable)

A throwaway local run of the whole app in Docker — Postgres, the API (which also serves the
web UI), and the poller worker — on local volumes. It starts with an **empty beets library**
that it creates itself. The point is to see it working and to see exactly what config a real
deploy needs; the real deploy points at your existing beets database and config instead.

## Run it

```sh
cd deploy
cp .env.example .env        # optional: add Spotify creds (see below)
docker compose up --build
```

Then open **http://localhost:8000** — the UI, the API, health, and metrics are all on that
one origin:

- UI: <http://localhost:8000>
- Health: <http://localhost:8000/health>
- Metrics (Prometheus): <http://localhost:8000/metrics>

Tear it down, keeping data: `docker compose down`.
Tear it down and **wipe** Postgres + the beets volume: `docker compose down -v`.

## What comes up

| Service    | What it is                                                              |
|------------|-------------------------------------------------------------------------|
| `postgres` | Postgres 16 on the `pgdata` volume.                                      |
| `init`     | One-shot: runs Alembic migrations and creates the empty beets library.  |
| `api`      | FastAPI (uvicorn) serving the API **and** the built SPA on port 8000.   |
| `worker`   | APScheduler running the pollers (ingest, reconcile, plays, watch, …).   |

The beets library (`library.db` + `music/` + `inbox/`) lives on the `beetsdata` volume, with
the config at [`beets/config.yaml`](beets/config.yaml) mounted read-only.

## Config

Infra wiring (DB URL, beets config path, import inbox, static dir) is set in
[`docker-compose.yml`](docker-compose.yml). Everything you might actually change — Spotify
credentials and the optional integrations — is in `.env`; see
[`.env.example`](.env.example) for the annotated list.

**Without Spotify credentials the app still boots** — it just shows "reconnect" and the
pollers stay paused, so no data flows in. To see the full loop, create a Spotify app at
<https://developer.spotify.com/dashboard>, add the redirect URI
`http://127.0.0.1:8000/auth/spotify/callback`, put the client id/secret in `.env`, restart
(`docker compose up -d`), and click **Reconnect** in the UI.

## For the real deploy

Nothing here is load-bearing. Point `WANTLIST_BEETS_CONFIG` at your existing beets config
(whose `library:`/`directory:` reference your real library, mounted where the container can
read it), point `WANTLIST_DATABASE_URL` at your real Postgres, and set the same `.env` values.
The image and compose services are otherwise the same.
