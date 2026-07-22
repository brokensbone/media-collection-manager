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


def test_reresolve_picks_up_release_once_it_appears_in_mb(
    clean_album_tables: sessionmaker[Session],
) -> None:
    """D17 periodic re-resolve: an album MB couldn't place stays a first-class want and is
    retried each pass — and resolves once MB grows to include it."""
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="Later")

    empty_mb = ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver({}),  # MB doesn't know it yet  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(),  # type: ignore[arg-type]
    )
    assert empty_mb.resolve_unresolved().resolved == 0

    grown_mb = ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver(
            {"Later": "rg-later"}
        ),  # MB now has it  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(),  # type: ignore[arg-type]
    )
    assert grown_mb.resolve_unresolved().resolved == 1
    assert AlbumRepo(sf).albums_needing_resolution() == []  # no longer in the tail


def test_unresolvable_albums_sink_so_fresh_ones_get_a_turn(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # With a capped pass and plain id order, a low-id album MB can't place would be re-ground
    # every run and starve higher-id resolvable ones forever. Least-tried-first must let the
    # fresh album through once the dead one has taken its turn.
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="Dead")  # lower id, never in MB
    _saved(sf, spotify_id="s2", title="Fresh")  # resolvable

    def svc() -> ResolutionService:
        return ResolutionService(
            api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
            resolver=StubMusicBrainzResolver({"Fresh": "rg-fresh"}),  # type: ignore[arg-type]
            repo=AlbumRepo(sf),
            tokens=StubTokens(),  # type: ignore[arg-type]
            max_per_run=1,
        )

    # pass 1: only the least-tried/lowest-id (Dead) is attempted → no-match, its attempt is counted
    assert svc().resolve_unresolved().resolved == 0
    # pass 2: Dead now has 1 attempt, Fresh has 0 → Fresh goes first this time and resolves
    assert svc().resolve_unresolved().resolved == 1


def test_resolution_pauses_on_reauth(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="X")
    assert _service(sf, fail_auth=True).resolve_unresolved().paused is True


def test_refreshes_the_token_per_album(clean_album_tables: sessionmaker[Session]) -> None:
    # The token must be fetched per album, not once per pass — else a long MB-throttled batch
    # outlives the token and 401s partway through.
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="Resolvable")
    _saved(sf, spotify_id="s2", title="Resolvable")
    tokens = StubTokens()
    ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver({"Resolvable": "rg-1"}),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=tokens,  # type: ignore[arg-type]
    ).resolve_unresolved()
    assert tokens.calls == 2  # one fresh token per album


def test_pauses_when_reauth_hits_mid_batch(clean_album_tables: sessionmaker[Session]) -> None:
    # If the refresh token dies partway through, resolve what we can and pause the rest.
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="Resolvable")
    _saved(sf, spotify_id="s2", title="Resolvable")
    result = ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver({"Resolvable": "rg-1"}),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(fail_after=1),  # type: ignore[arg-type]
    ).resolve_unresolved()
    assert result.paused is True
    assert result.resolved == 1  # the first album resolved before the token died
