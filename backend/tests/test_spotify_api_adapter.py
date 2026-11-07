import httpx
import pytest
import respx

from mcm.adapters.spotify_api import HttpxSpotifyApiClient

API = "https://api.test/v1"


@respx.mock
def test_transient_failures_back_off_and_retry_current_page(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr("mcm.adapters.spotify_api.time.sleep", sleeps.append)
    first = respx.get(f"{API}/me/albums?limit=50").respond(
        200, json={"items": [{"album": {"id": "a1", "name": "First"}}], "next": f"{API}/next"}
    )
    page = respx.get(f"{API}/next").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("TLS EOF"),
            httpx.Response(504),
            httpx.Response(200, json={"items": [], "next": None}),
        ]
    )
    albums = list(HttpxSpotifyApiClient(API, 300).saved_albums("secret"))
    assert [album.spotify_id for album in albums] == ["a1"]
    assert first.call_count == 1
    assert page.call_count == 4
    assert sleeps == [2, 4, 8]


@respx.mock
@pytest.mark.parametrize("status,attempts", [(401, 1), (403, 1), (404, 1), (503, 6)])
def test_permanent_or_exhausted_failure_propagates(monkeypatch, status, attempts) -> None:
    sleeps = []
    monkeypatch.setattr("mcm.adapters.spotify_api.time.sleep", sleeps.append)
    route = respx.get(f"{API}/artists/artist/albums").respond(status)
    with pytest.raises(httpx.HTTPStatusError):
        HttpxSpotifyApiClient(API, 300).artist_albums("secret", "artist")
    assert route.call_count == attempts
    assert sleeps == [2, 4, 8, 16, 32][: attempts - 1]


@respx.mock
def test_artist_retry_honours_rate_limit(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr("mcm.adapters.spotify_api.time.sleep", sleeps.append)
    respx.get(f"{API}/artists/artist/albums").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "10"}),
            httpx.Response(200, json={"items": []}),
        ]
    )
    assert HttpxSpotifyApiClient(API, 300).artist_albums("secret", "artist") == []
    assert sleeps == [10]


@respx.mock
def test_saved_albums_paginates_and_parses() -> None:
    page2 = f"{API}/me/albums?offset=1"
    respx.get(f"{API}/me/albums?limit=50").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "added_at": "2026-06-01T00:00:00Z",
                        "album": {
                            "id": "a1",
                            "name": "Alb One",
                            "artists": [{"name": "Artist X", "id": "artX"}],
                            "external_ids": {"upc": "111"},
                            "images": [
                                {"url": "big", "width": 640},
                                {"url": "mid", "width": 300},
                            ],
                        },
                    }
                ],
                "next": page2,
            },
        )
    )
    respx.get(page2).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "added_at": None,
                        "album": {
                            "id": "a2",
                            "name": "Alb Two",
                            "artists": [{"name": "Y"}, {"name": "Z"}],
                            "external_ids": {},
                            "images": [],
                        },
                    }
                ],
                "next": None,
            },
        )
    )

    albums = list(HttpxSpotifyApiClient(API, art_target_px=300).saved_albums("tok"))

    assert [a.spotify_id for a in albums] == ["a1", "a2"]
    assert albums[0].artist == "Artist X"
    assert albums[0].artist_id == "artX"
    assert albums[0].upc == "111"
    assert albums[0].art_url == "mid"  # closest to the 300px target
    assert albums[0].added_at is not None
    assert albums[1].artist == "Y, Z"
    assert albums[1].art_url is None
