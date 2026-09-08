from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.artist_watch import ArtistWatchService
from wantlist.ports.spotify_api import SavedAlbum

from .fakes import StubSpotifyApiClient, StubTokens


def _rel(spotify_id: str, artist_id: str = "artA") -> SavedAlbum:
    return SavedAlbum(spotify_id, "The Band", artist_id, spotify_id, None, None, None)


def _svc(sf: sessionmaker[Session], api: StubSpotifyApiClient) -> ArtistWatchService:
    return ArtistWatchService(api=api, repo=AlbumRepo(sf), tokens=StubTokens())  # type: ignore[arg-type]


def test_first_run_baselines_without_surfacing(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    api = StubSpotifyApiClient(followed=["artA"], artist_albums={"artA": [_rel("a1"), _rel("a2")]})
    result = _svc(sf, api).poll()
    assert result.baselined == 1
    assert result.added == 0  # whole catalogue recorded as seen, nothing surfaced
    assert AlbumRepo(sf).suggested_queue() == []


def test_second_run_surfaces_only_new_releases(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    catalogue = [_rel("a1"), _rel("a2")]
    api = StubSpotifyApiClient(followed=["artA"], artist_albums={"artA": catalogue})
    _svc(sf, api).poll()  # baseline a1, a2

    catalogue.append(_rel("a3"))  # a genuinely new release
    result = _svc(sf, api).poll()
    assert result.added == 1
    assert [r.title for r in AlbumRepo(sf).suggested_queue()] == ["a3"]


def test_already_tracked_album_is_not_resurfaced(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    catalogue = [_rel("a1")]
    api = StubSpotifyApiClient(followed=["artA"], artist_albums={"artA": catalogue})
    _svc(sf, api).poll()  # baseline a1

    AlbumRepo(sf).add_saved_album(
        spotify_id="a2",
        artist="The Band",
        artist_id="artA",
        title="a2",
        upc=None,
        added_at=None,
        art_url=None,
    )
    catalogue.append(_rel("a2"))  # appears in the catalogue but we already saved it
    result = _svc(sf, api).poll()
    assert result.added == 0  # already tracked → not surfaced as a suggestion
