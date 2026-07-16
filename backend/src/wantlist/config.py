from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The environment contract (SPEC §8a). All from env (WANTLIST_*) or a .env file."""

    model_config = SettingsConfigDict(env_prefix="WANTLIST_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "postgresql+psycopg://localhost:5432/wantlist"

    # beets seam (§5): the command may be `beet`, `docker exec … beet`, `ssh … beet`, etc.
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
