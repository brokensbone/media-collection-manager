from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.models import Album, AlbumState, Provenance
from mcm.releases import ReleasesService

from .fakes import FrozenClock, StubSpotifyApiClient, StubTokens

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _suggested(sf: sessionmaker[Session], title: str) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=f"sp-{title}",
                artist="A",
                artist_id="art1",
                title=title,
                state=AlbumState.suggested,
                provenance=Provenance.artist_watch,
            )
        )
        session.commit()


def _svc(sf: sessionmaker[Session], api: StubSpotifyApiClient) -> ReleasesService:
    return ReleasesService(api=api, repo=AlbumRepo(sf), tokens=StubTokens(), clock=FrozenClock(NOW))  # type: ignore[arg-type]


def _id(sf: sessionmaker[Session], title: str) -> int:
    return next(a.id for a in AlbumRepo(sf).list_albums() if a.title == title)


def test_queue_lists_suggested(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _suggested(sf, "New One")
    assert [r.title for r in _svc(sf, StubSpotifyApiClient()).queue()] == ["New One"]


def test_save_writes_to_spotify_and_enters_flow(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _suggested(sf, "New One")
    api = StubSpotifyApiClient()
    _svc(sf, api).save(_id(sf, "New One"))
    assert api.saved_calls == ["sp-New One"]  # wrote to the Spotify library
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"New One": "saved"}
    assert _svc(sf, api).queue() == []  # left the Releases queue


def test_want_saves_and_jumps_to_wanted(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _suggested(sf, "New One")
    api = StubSpotifyApiClient()
    _svc(sf, api).want(_id(sf, "New One"))
    assert api.saved_calls == ["sp-New One"]
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"New One": "wanted"}


def test_dismiss_does_not_write(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _suggested(sf, "New One")
    api = StubSpotifyApiClient()
    _svc(sf, api).dismiss(_id(sf, "New One"))
    assert api.saved_calls == []
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"New One": "dismissed"}
