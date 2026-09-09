from dataclasses import dataclass
from typing import Protocol


class ReauthRequired(Exception):
    """Raised when Spotify refuses a refresh (`invalid_grant`) — the 6-month expiry (§8c).
    The user must re-authorize; pollers pause until then."""


@dataclass
class SpotifyTokens:
    access_token: str
    refresh_token: str
    expires_in: int  # seconds


class SpotifyAuthClient(Protocol):
    """The OAuth surface we depend on (SPEC §8c). Adapter uses a configurable base URL."""

    def authorize_url(self, state: str) -> str: ...

    def exchange_code(self, code: str) -> SpotifyTokens: ...

    def refresh(self, refresh_token: str) -> SpotifyTokens: ...


class AccessTokenProvider(Protocol):
    """A valid access token for API calls; raises ReauthRequired when re-auth is needed."""

    def valid_access_token(self) -> str: ...
