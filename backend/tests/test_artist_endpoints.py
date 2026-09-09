import httpx
import respx

from mcm.adapters.spotify_api import HttpxSpotifyApiClient

API = "https://api.test/v1"


@respx.mock
def test_followed_artist_ids_paginates() -> None:
    page2 = f"{API}/me/following?type=artist&after=x"
    respx.get(f"{API}/me/following?type=artist&limit=50").mock(
        return_value=httpx.Response(200, json={"artists": {"items": [{"id": "a1"}], "next": page2}})
    )
    respx.get(page2).mock(
        return_value=httpx.Response(200, json={"artists": {"items": [{"id": "a2"}], "next": None}})
    )
    assert HttpxSpotifyApiClient(API, 300).followed_artist_ids("tok") == ["a1", "a2"]


@respx.mock
def test_artist_albums_parses_and_scopes_to_market() -> None:
    # market must be sent — it dedupes Spotify's per-country album variants (else old releases
    # resurface as new) and limits results to what's playable in that market.
    route = respx.get(f"{API}/artists/art1/albums?include_groups=album&limit=50&market=GB").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "alb1",
                        "name": "New One",
                        "artists": [{"name": "The Band", "id": "art1"}],
                        "images": [],
                    }
                ],
                "next": None,
            },
        )
    )
    albums = HttpxSpotifyApiClient(API, 300, market="GB").artist_albums("tok", "art1")
    assert route.called
    assert albums[0].spotify_id == "alb1"
    assert albums[0].artist_id == "art1"
    assert albums[0].added_at is None


@respx.mock
def test_save_album_puts_to_library() -> None:
    route = respx.put(f"{API}/me/albums").mock(return_value=httpx.Response(200))
    HttpxSpotifyApiClient(API, 300).save_album("tok", "alb1")
    assert route.called
    assert route.calls.last.request.url.params["ids"] == "alb1"
