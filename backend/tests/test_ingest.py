from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.ingest import IngestService
from wantlist.models import Album, AlbumState, Provenance
from wantlist.ports.spotify_api import SavedAlbum

from .fakes import StubSpotifyApiClient, StubTokens, fake_fetch_image

ALBUMS = [
    SavedAlbum("a1", "Artist", "art-1", "One", None, None, "http://art/1"),
    SavedAlbum("a2", "Artist", "art-1", "Two", None, None, None),
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


def _add_owned_artless(sf: sessionmaker[Session], *, artist: str, title: str) -> None:
    with sf() as session:
        session.add(
            Album(
                artist=artist,
                title=title,
                state=AlbumState.owned,
                provenance=Provenance.manual,  # no art_url — like a Transmission import
            )
        )
        session.commit()


def _backfill_service(
    sf: sessionmaker[Session], search: dict[str, SavedAlbum], *, fail_auth: bool = False
) -> IngestService:
    return IngestService(
        api=StubSpotifyApiClient(search=search),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(fail=fail_auth),  # type: ignore[arg-type]
        fetch_image=fake_fetch_image,
    )


def test_backfill_owned_art_sets_url_from_spotify(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add_owned_artless(sf, artist="Aesop Rock", title="Skelethon")
    found = SavedAlbum("sp9", "Aesop Rock", None, "Skelethon", None, None, "http://art/aesop")

    svc = _backfill_service(sf, {"Aesop Rock Skelethon": found})
    assert svc.backfill_owned_art() == 1
    # the album now has an art_url and is picked up by the normal art fetch
    assert AlbumRepo(sf).owned_without_art() == []
    assert len(AlbumRepo(sf).albums_missing_art()) == 1


def test_backfill_owned_art_pauses_when_spotify_disconnected(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add_owned_artless(sf, artist="Aesop Rock", title="Skelethon")
    svc = _backfill_service(sf, {}, fail_auth=True)
    assert svc.backfill_owned_art() == 0
    assert len(AlbumRepo(sf).owned_without_art()) == 1  # still artless, retries next pass
