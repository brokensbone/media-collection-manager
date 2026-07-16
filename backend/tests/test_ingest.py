from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.ingest import IngestService
from wantlist.ports.spotify_api import SavedAlbum

from .fakes import StubSpotifyApiClient, StubTokens, fake_fetch_image

ALBUMS = [
    SavedAlbum("a1", "Artist", "One", None, None, "http://art/1"),
    SavedAlbum("a2", "Artist", "Two", None, None, None),
]


def _service(sf: sessionmaker[Session], *, fail_auth: bool = False) -> IngestService:
    return IngestService(
        api=StubSpotifyApiClient(ALBUMS),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(fail=fail_auth),  # type: ignore[arg-type]
        fetch_image=fake_fetch_image,
    )


def test_ingest_adds_then_dedups(clean_album_tables: sessionmaker[Session]) -> None:
    svc = _service(clean_album_tables)
    first = svc.ingest_saves()
    assert (first.added, first.skipped, first.paused) == (2, 0, False)
    second = svc.ingest_saves()
    assert (second.added, second.skipped, second.paused) == (0, 2, False)
    assert AlbumRepo(clean_album_tables).existing_spotify_ids() == {"a1", "a2"}


def test_ingest_pauses_on_reauth(clean_album_tables: sessionmaker[Session]) -> None:
    result = _service(clean_album_tables, fail_auth=True).ingest_saves()
    assert result.paused is True
    assert result.added == 0
    assert AlbumRepo(clean_album_tables).existing_spotify_ids() == set()


def test_fetch_missing_art_stores_only_albums_with_url(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _service(clean_album_tables)
    svc.ingest_saves()
    stored = svc.fetch_missing_art()
    assert stored == 1  # only a1 has an art_url
    assert AlbumRepo(clean_album_tables).albums_missing_art() == []
