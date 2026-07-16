from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The environment contract (SPEC §8a). All from env (WANTLIST_*) or a .env file."""

    model_config = SettingsConfigDict(env_prefix="WANTLIST_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "postgresql+psycopg://localhost:5432/wantlist"

    # beets seam (§5): beets is bundled, so the main knob is a path to the beets config
    # (its `library:`/`directory:` point at the mounted library.db + music). `beets_command`
    # defaults to the bundled `beet`; override only for a genuinely-remote beets (ssh/exec).
    beets_command: str = "beet"
    beets_config: str | None = None

    # Spotify (§8c). Base URLs are overridable so E2E can point at a stub (§14).
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/spotify/callback"
    spotify_scopes: str = "user-library-read"  # §6b adds user-library-modify
    spotify_accounts_url: str = "https://accounts.spotify.com"
    spotify_api_url: str = "https://api.spotify.com/v1"

    # Re-auth countdown (§8c): refresh tokens expire ~6 months after authorization.
    reauth_lifetime_days: int = 183
    reauth_warn_days: int = 21

    # Where to send the browser after a successful callback.
    frontend_url: str = "/"

    # Ingest (§4/§4b): poll interval and the cover-art size to keep.
    saves_poll_seconds: int = 3600
    art_target_px: int = 300

    # MusicBrainz resolution (§5, §11). Base URL overridable for tests/E2E (§14).
    musicbrainz_url: str = "https://musicbrainz.org/ws/2"
    musicbrainz_user_agent: str = "wantlist/0.1 ( https://github.com/EdwardSalkeld )"
    musicbrainz_min_interval: float = 1.1  # MB asks for <= 1 req/sec
    musicbrainz_text_min_score: int = 90  # Tier-3 fuzzy accept threshold
