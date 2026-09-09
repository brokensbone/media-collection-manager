import httpx
import pytest
import respx

from mcm.adapters.spotify_auth import HttpxSpotifyAuthClient
from mcm.ports.spotify import ReauthRequired

ACCOUNTS = "https://accounts.test"


def _client() -> HttpxSpotifyAuthClient:
    return HttpxSpotifyAuthClient(
        client_id="cid",
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8000/auth/spotify/callback",
        scopes="user-library-read",
        accounts_url=ACCOUNTS,
    )


def test_authorize_url_contains_params() -> None:
    url = _client().authorize_url("xyz")
    assert url.startswith(f"{ACCOUNTS}/authorize?")
    assert "client_id=cid" in url
    assert "scope=user-library-read" in url
    assert "state=xyz" in url


@respx.mock
def test_exchange_code_returns_tokens() -> None:
    respx.post(f"{ACCOUNTS}/api/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "a", "refresh_token": "r", "expires_in": 3600}
        )
    )
    tokens = _client().exchange_code("the-code")
    assert tokens.access_token == "a"
    assert tokens.refresh_token == "r"


@respx.mock
def test_refresh_reuses_refresh_token_when_omitted() -> None:
    respx.post(f"{ACCOUNTS}/api/token").mock(
        return_value=httpx.Response(200, json={"access_token": "a2", "expires_in": 3600})
    )
    tokens = _client().refresh("old-refresh")
    assert tokens.access_token == "a2"
    assert tokens.refresh_token == "old-refresh"


@respx.mock
def test_refresh_invalid_grant_raises_reauth() -> None:
    respx.post(f"{ACCOUNTS}/api/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(ReauthRequired):
        _client().refresh("expired-refresh")
