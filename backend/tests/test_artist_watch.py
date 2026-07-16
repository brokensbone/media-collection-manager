from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.artist_watch import ArtistWatchService
from wantlist.models import Album, AlbumState, Provenance
from wantlist.ports.spotify_api import SavedAlbum

from .fakes import StubSpotifyApiClient, StubTokens


def _release(album_id: str, artist_id: str) -> SavedAlbum:
    return SavedAlbum(album_id, "The Band", artist_id, "New Album", None, None, None)


def _kept_album(sf: sessionmaker[Session], artist_id: str) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=f"owned-{artist_id}",
                artist="The Band",
                artist_id=artist_id,
                title="Owned",
                state=AlbumState.owned,
                provenance=Provenance.spotify_save,
            )
        )
        session.commit()


def test_watch_surfaces_new_releases_from_followed_and_kept(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _kept_album(sf, "keptArtist")  # seeds a kept-artist id
    api = StubSpotifyApiClient(
        followed=["followedArtist"],
        artist_albums={
            "followedArtist": [_release("relF", "followedArtist")],
            "keptArtist": [_release("relK", "keptArtist")],
        },
    )
    result = ArtistWatchService(api=api, repo=AlbumRepo(sf), tokens=StubTokens()).poll()  # type: ignore[arg-type]
    assert result.added == 2
    assert result.artists == 2  # followed ∪ kept
    assert len(AlbumRepo(sf).suggested_queue()) == 2


def test_watch_dedupes_known_albums(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _kept_album(sf, "keptArtist")  # spotify_id owned-keptArtist already exists
    api = StubSpotifyApiClient(
        followed=[],
        artist_albums={"keptArtist": [_release("owned-keptArtist", "keptArtist")]},
    )
    result = ArtistWatchService(api=api, repo=AlbumRepo(sf), tokens=StubTokens()).poll()  # type: ignore[arg-type]
    assert result.added == 0  # already known → not re-suggested
