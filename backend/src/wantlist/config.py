from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The environment contract (SPEC §8a). All from env (WANTLIST_*) or a .env file."""

    model_config = SettingsConfigDict(env_prefix="WANTLIST_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "postgresql+psycopg://localhost:5432/wantlist"

    # beets seam (§5): the command may be `beet`, `docker exec … beet`, `ssh … beet`, etc.
    beets_command: str = "beet"
    beets_config: str | None = None
