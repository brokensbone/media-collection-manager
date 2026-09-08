from datetime import timedelta

from .adapters.token_store import TokenStore
from .domain.auth import AuthStatus, compute_status
from .ports.clock import Clock
from .ports.spotify import ReauthRequired, SpotifyAuthClient

_ACCESS_REFRESH_BUFFER = timedelta(seconds=60)


class AuthService:
    """Owns the Spotify OAuth lifecycle: login, token refresh, re-auth, status (§8c)."""

    def __init__(
        self,
        *,
        client: SpotifyAuthClient,
        store: TokenStore,
        clock: Clock,
        scopes: str,
        lifetime_days: int,
        warn_days: int,
    ) -> None:
        self._client = client
        self._store = store
        self._clock = clock
        self._scopes = scopes
        self._lifetime_days = lifetime_days
        self._warn_days = warn_days

    def authorize_url(self, state: str) -> str:
        return self._client.authorize_url(state)

    def complete_login(self, code: str) -> None:
        tokens = self._client.exchange_code(code)
        now = self._clock.now()
        self._store.save_authorization(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            access_expires_at=now + timedelta(seconds=tokens.expires_in),
            authorized_at=now,
            scopes=self._scopes,
        )

    def valid_access_token(self) -> str:
        """Return a usable access token, refreshing if needed. Raises ReauthRequired if the
        refresh token has expired — callers (pollers) pause until the user reconnects."""
        stored = self._store.load()
        if not stored.refresh_token:
            raise ReauthRequired
        now = self._clock.now()
        if (
            stored.access_token
            and stored.access_expires_at
            and stored.access_expires_at > now + _ACCESS_REFRESH_BUFFER
        ):
            return stored.access_token
        try:
            tokens = self._client.refresh(stored.refresh_token)
        except ReauthRequired:
            self._store.clear()
            raise
        self._store.save_refreshed(
            access_token=tokens.access_token,
            access_expires_at=now + timedelta(seconds=tokens.expires_in),
        )
        return tokens.access_token

    def status(self) -> AuthStatus:
        stored = self._store.load()
        return compute_status(
            connected=bool(stored.refresh_token),
            authorized_at=stored.authorized_at,
            now=self._clock.now(),
            lifetime_days=self._lifetime_days,
            warn_days=self._warn_days,
        )
