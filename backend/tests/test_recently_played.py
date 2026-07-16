import httpx
import respx

from wantlist.adapters.spotify_api import HttpxSpotifyApiClient

API = "https://api.test/v1"


@respx.mock
def test_recently_played_parses_plays() -> None:
    respx.get(f"{API}/me/player/recently-played?limit=50").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "played_at": "2026-07-15T10:00:00Z",
                        "track": {"id": "t1", "album": {"id": "alb1"}},
                    },
                    {"played_at": "2026-07-15T09:00:00Z", "track": {"id": "t2", "album": {}}},
                    {"played_at": "2026-07-15T08:00:00Z", "track": {}},  # no track id → skipped
                ]
            },
        )
    )
    plays = HttpxSpotifyApiClient(API, art_target_px=300).recently_played("tok")
    assert [p.spotify_track_id for p in plays] == ["t1", "t2"]
    assert plays[0].spotify_album_id == "alb1"
    assert plays[1].spotify_album_id is None
