from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.models import Album, AlbumState, Provenance
from wantlist.resolution import ResolutionService

from .fakes import StubMusicBrainzResolver, StubSpotifyApiClient, StubTokens


def _saved(sf: sessionmaker[Session], *, spotify_id: str, title: str) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=spotify_id,
                artist="A",
                title=title,
                state=AlbumState.saved,
                provenance=Provenance.spotify_save,
            )
        )
        session.commit()


def _service(sf: sessionmaker[Session], *, fail_auth: bool = False) -> ResolutionService:
    return ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver({"Resolvable": "rg-1"}),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(fail=fail_auth),  # type: ignore[arg-type]
    )


def test_resolution_sets_release_group_and_leaves_tail(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="Resolvable")
    _saved(sf, spotify_id="s2", title="Unresolvable")

    first = _service(sf).resolve_unresolved()
    assert (first.resolved, first.unresolved, first.paused) == (1, 1, False)

    # resolve-once: the resolved album is no longer a candidate; only the tail retries
    second = _service(sf).resolve_unresolved()
    assert (second.resolved, second.unresolved) == (0, 1)


def test_resolution_pauses_on_reauth(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="X")
    assert _service(sf, fail_auth=True).resolve_unresolved().paused is True
