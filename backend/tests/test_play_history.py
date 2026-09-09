from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.play_history import PlayHistoryService
from mcm.ports.spotify_api import Play

from .fakes import StubSpotifyApiClient, StubTokens

T0 = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 15, 11, 0, tzinfo=UTC)


def test_add_plays_dedupes_on_track_and_time(clean_album_tables: sessionmaker[Session]) -> None:
    repo = AlbumRepo(clean_album_tables)
    plays = [Play("t1", "alb1", T0), Play("t2", "alb1", T1)]
    assert repo.add_plays(plays) == 2
    assert repo.add_plays(plays) == 0  # same (track, played_at) → ignored
    stats = repo.play_stats_by_album()
    assert stats["alb1"].distinct_tracks == 2


def test_poll_inserts_and_pauses_on_reauth(clean_album_tables: sessionmaker[Session]) -> None:
    repo = AlbumRepo(clean_album_tables)
    api = StubSpotifyApiClient(plays=[Play("t1", "alb1", T0)])

    ok = PlayHistoryService(api=api, repo=repo, tokens=StubTokens()).poll()  # type: ignore[arg-type]
    assert ok.added == 1 and ok.paused is False

    paused = PlayHistoryService(
        api=api,
        repo=repo,
        tokens=StubTokens(fail=True),  # type: ignore[arg-type]
    ).poll()
    assert paused.paused is True and paused.added == 0
