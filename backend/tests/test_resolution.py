from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.models import Album, AlbumState, Provenance
from wantlist.resolution import ResolutionService

from .fakes import StubMusicBrainzResolver, StubSpotifyApiClient, StubTokens


class _BoomResolver:
    """A MusicBrainz resolver that always fails to reach MB (stands in for a 503/outage)."""

    def resolve(self, *, upc: str | None, isrcs: list[str], artist: str, title: str) -> str | None:
        raise RuntimeError("MusicBrainz unreachable")


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
        backoff_base_seconds=0,  # these tests exercise resolve logic, not the backoff gate
    )


_NO_BACKOFF = {"backoff_base_seconds": 0, "backoff_cap_seconds": 0}


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
        backoff_base_seconds=0,  # re-resolve immediately here; backoff is tested separately
    )
    assert empty_mb.resolve_unresolved().resolved == 0

    grown_mb = ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver(
            {"Later": "rg-later"}
        ),  # MB now has it  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(),  # type: ignore[arg-type]
        backoff_base_seconds=0,
    )
    assert grown_mb.resolve_unresolved().resolved == 1
    assert AlbumRepo(sf).albums_needing_resolution(**_NO_BACKOFF) == []  # no longer in the tail


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
            backoff_base_seconds=0,  # isolate the least-tried ordering from the backoff gate
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


def _absent_service(sf: sessionmaker[Session]) -> ResolutionService:
    # MB never has the album → every pass is a "no match", exercising the backoff gate with the
    # real (default) window rather than the base=0 opt-out the logic tests use.
    return ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=StubMusicBrainzResolver({}),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(),  # type: ignore[arg-type]
        backoff_base_seconds=3600,
        backoff_cap_seconds=604800,
    )


def test_no_match_backs_off_then_retries_once_the_window_elapses(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="Absent")  # MB never has it

    # pass 1: attempted, no match — backoff stamped (attempts=1 → ~2h window)
    r1 = _absent_service(sf).resolve_unresolved()
    assert (r1.resolved, r1.unresolved) == (0, 1)

    # pass 2 immediately after: still inside the backoff window → not due, not re-queried
    r2 = _absent_service(sf).resolve_unresolved()
    assert (r2.resolved, r2.unresolved) == (0, 0)

    # age the last attempt past the window → due again
    with sf() as session:
        album = session.scalars(select(Album)).one()
        album.last_resolution_attempt = datetime.now(UTC) - timedelta(hours=3)
        session.commit()
    r3 = _absent_service(sf).resolve_unresolved()
    assert (r3.resolved, r3.unresolved) == (0, 1)


def test_circuit_breaker_aborts_the_pass_after_consecutive_errors(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    for i in range(10):
        _saved(sf, spotify_id=f"s{i}", title=f"t{i}")

    result = ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=_BoomResolver(),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(),  # type: ignore[arg-type]
        error_circuit_break=3,
        backoff_base_seconds=0,
    ).resolve_unresolved()

    # MB is down: bail after 3 consecutive errors rather than grinding all 10 (and logging 10)
    assert result.unresolved == 3
    assert result.resolved == 0


def test_upstream_error_does_not_advance_the_backoff(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # An outage must not count as an attempt: the album stays due (last_resolution_attempt unset,
    # attempts unchanged) so it's retried promptly once MB is back, not pushed out to the cap.
    sf = clean_album_tables
    _saved(sf, spotify_id="s1", title="X")

    ResolutionService(
        api=StubSpotifyApiClient([]),  # type: ignore[arg-type]
        resolver=_BoomResolver(),  # type: ignore[arg-type]
        repo=AlbumRepo(sf),
        tokens=StubTokens(),  # type: ignore[arg-type]
    ).resolve_unresolved()

    with sf() as session:
        album = session.scalars(select(Album)).one()
        assert album.resolution_attempts == 0
        assert album.last_resolution_attempt is None
    still_due = AlbumRepo(sf).albums_needing_resolution(
        backoff_base_seconds=3600, backoff_cap_seconds=604800
    )
    assert len(still_due) == 1
