# Deploy

Two self-contained Docker Compose setups, each a plain `docker compose up -d` from its own
directory (they share the [`Dockerfile`](Dockerfile)):

- [`local/`](local) — a disposable local run: Postgres in a container, an empty beets library
  it creates itself. For seeing it work and what config a real deploy needs.
- [`prod/`](prod) — an example production-shaped deployment: app + worker with an external
  Postgres database and a bind-mounted beets library.

## Local (disposable)

```sh
cd deploy/local
cp .env.example .env        # optional: add Spotify creds (see below)
docker compose up -d --build
```

Then open **http://localhost:8000** — UI, API, health (`/health`) and metrics (`/metrics`) are
all on that one origin.

Tear down keeping data: `docker compose down`. Wipe Postgres + the beets volume too:
`docker compose down -v`.

| Service    | What it is                                                              |
|------------|-------------------------------------------------------------------------|
| `postgres` | Postgres 16 on the `pgdata` volume.                                     |
| `init`     | One-shot: runs Alembic migrations and creates the empty beets library. |
| `api`      | FastAPI (uvicorn) serving the API **and** the built SPA on port 8000.  |
| `worker`   | APScheduler running the pollers (ingest, reconcile, plays, watch, …).  |

The beets library (`library.db` + `music/` + `inbox/`) lives on the `beetsdata` volume, config
at [`local/beets/config.yaml`](local/beets/config.yaml). Everything you'd change is in `.env`
(see [`local/.env.example`](local/.env.example)).

**Without Spotify credentials the app still boots** — it shows "reconnect" and the pollers stay
paused. To see the full loop, create a Spotify app at
<https://developer.spotify.com/dashboard>, add the redirect URI
`http://127.0.0.1:8000/auth/spotify/callback`, put the client id/secret in `.env`, restart
(`docker compose up -d`), and click **Reconnect**.

## Prod

```sh
cd deploy/prod
cp .env.example .env        # fill in the placeholders
docker compose up -d --build
```

App + worker only — use an external Postgres database and bind-mount your existing beets library.
Fill [`prod/.env.example`](prod/.env.example): point `WANTLIST_DATABASE_URL` at the database,
set `WANTLIST_BEETS_DIR` to your beets directory (the app runs beets with `BEETSDIR` set to it,
so beets finds its own config + library there), and set the music dir to its real absolute path
(see below).

### Beets paths must be host-consistent

beets stores **absolute** file paths in `library.db` (one per track, under its `directory:`),
and it runs *inside* the container. So the music directory must be mounted at the **same
absolute path** on the host and in the container, and `directory:` must equal that path.

Mount your real library at its own path, e.g.:

```yaml
volumes:
  - /srv/music:/srv/music      # NOT /srv/music:/beets/music
```

with `directory: /srv/music` in the beets config. Then every path beets reads or writes is
valid on the host too, and matches what your existing `library.db` already records — no
rewrite, no surprises.

**Don't** mount the library at a different container path than the host path (e.g. a host dir
onto `/beets/music`, or a Docker named volume). beets would then record container-only paths
that don't resolve anywhere else — imports "work" but the library is wrong the moment beets
runs outside that exact container. (The disposable local deploy uses a `beetsdata` volume
precisely because it's throwaway; don't copy that pattern to production.)
