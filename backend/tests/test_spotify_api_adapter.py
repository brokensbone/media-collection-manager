import httpx
import respx

from mcm.adapters.spotify_api import HttpxSpotifyApiClient

API = "https://api.test/v1"


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
