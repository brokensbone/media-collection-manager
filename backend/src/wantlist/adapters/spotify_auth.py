import base64
import urllib.parse

import httpx

from ..ports.spotify import ReauthRequired, SpotifyTokens


class HttpxSpotifyAuthClient:
    """Authorization Code flow with client secret over httpx (SPEC §8c, §15).
    Base URL is injected so tests/E2E can point it at a stub (§14)."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: str,
        accounts_url: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes
        self._accounts_url = accounts_url.rstrip("/")

    def authorize_url(self, state: str) -> str:
        params = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "response_type": "code",
                "redirect_uri": self._redirect_uri,
                "scope": self._scopes,
                "state": state,
            }
        )
        return f"{self._accounts_url}/authorize?{params}"

    def exchange_code(self, code: str) -> SpotifyTokens:
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
            }
        )

    def refresh(self, refresh_token: str) -> SpotifyTokens:
        tokens = self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            keep_refresh_token=refresh_token,
        )
        return tokens

    def _token_request(
        self, data: dict[str, str], keep_refresh_token: str | None = None
    ) -> SpotifyTokens:
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        resp = httpx.post(
            f"{self._accounts_url}/api/token",
            headers={"Authorization": f"Basic {basic}"},
            data=data,
            timeout=30,
        )
        if resp.status_code == 400 and resp.json().get("error") == "invalid_grant":
            raise ReauthRequired
        resp.raise_for_status()
        body = resp.json()
        return SpotifyTokens(
            access_token=body["access_token"],
            # refresh-token responses may omit a new refresh token — reuse the old one.
            refresh_token=body.get("refresh_token") or keep_refresh_token or "",
            expires_in=body.get("expires_in", 3600),
        )
