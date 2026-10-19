# Deploy

## Optional Navidrome radio destination

Navidrome sync is independent of MPD. No programmes are selected by default. After applying
the database migrations, configure the **worker** with `MCM_NAVIDROME_URL` (server base URL,
including any reverse-proxy prefix, without `/rest`) and `MCM_NAVIDROME_API_KEY`. Servers
without OpenSubsonic API-key support can use `MCM_NAVIDROME_USERNAME` and
`MCM_NAVIDROME_PASSWORD` instead (salted token authentication). Keep these in deployment
secrets, not the repository. A dedicated playlist-owning account is recommended.

For an existing programme:

```http
PUT /radio/schedules/2026-10-19/navidrome
Content-Type: application/json

{"enabled": true}
```

The API returns 202 with a durable `pending` state. The worker processes selected programmes
at startup and every `MCM_NAVIDROME_POLL_SECONDS` (default 60). Programme edits automatically
queue another sync. Repeating this PUT requests an independent retry, including after manual
Navidrome edits. Read `GET /radio/schedules/2026-10-19/navidrome` for enabled/status,
playlist ID, last attempt/success, last successful track count, error and unmatched relative
file paths. States are `disabled`, `pending`, `synced`, and `error`; errors retry on the next
poll. Without worker configuration, requests remain pending.

Set `{"enabled": false}` to stop future syncs. This retains the remote playlist and its saved
ID, so enabling again updates the same copy. No MPD action selects or syncs to Navidrome.
The existing MPD scheduling behaviour is unchanged. This change adds API controls only.

Navidrome normally reports virtual filenames derived from tags, even when the files are on
the same machine. **Enable Report Real Path for the MCM player in Navidrome Settings →
Players** after its first connection (displayed as `MCM [MCM]`; HTTP user agent `MCM/1`). A stable user agent
keeps this player setting across HTTP-library updates. Virtual paths are rejected before
any playlist writes.
Set `MCM_NAVIDROME_PATH_PREFIX` to the absolute music root Navidrome sees; if omitted, the
worker uses `MCM_MUSIC_DIR`. This strips the service's mount root before matching.

Songs are indexed through paginated OpenSubsonic `search3` and matched by exact relative
file path, including case and extension. Order and repeated selections are preserved. If
the two services see different mount roots, use Navidrome's root for the prefix; unrelated
roots are rejected. For multiple
music folders, `MCM_NAVIDROME_MUSIC_FOLDER_ID` can restrict matching to one. Missing,
unscanned or ambiguous paths fail the entire sync before changing a playlist: no fuzzy
recording substitutions or silently truncated programmes. Album selections with unavailable
paths also fail rather than dropping tracks.

Playlists are named `MCM Radio — YYYY-MM-DD`. Reserve these names for MCM in the configured
account: after a lost create response the worker recovers a unique playlist with this name;
multiple matches require manual cleanup. Later writes use the saved remote ID and verify the
returned song order by reading the playlist back. A deleted remote playlist is reported as
an error rather than silently creating a replacement. Credentials and song lists use form
POST bodies rather than URLs. Keep the configured server/account stable once IDs are saved.

API reference: [OpenSubsonic playlists](https://opensubsonic.netlify.app/docs/endpoints/createplaylist/),
[catalogue pagination](https://opensubsonic.netlify.app/docs/endpoints/search3/),
[API-key authentication](https://opensubsonic.netlify.app/docs/extensions/apikeyauth/).

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
Fill [`prod/.env.example`](prod/.env.example): point `MCM_DATABASE_URL` at the database,
set `MCM_BEETS_DIR` to your beets directory (the app runs beets with `BEETSDIR` set to it,
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
