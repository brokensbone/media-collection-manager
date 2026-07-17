from datetime import UTC, datetime, timedelta

from wantlist.domain.verdict import ZERO_PLAYS, PlayStat, forgotten_reason, verdict_reason

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _reason(saved_days: int | None, stat: PlayStat) -> str | None:
    saved_at = None if saved_days is None else NOW - timedelta(days=saved_days)
    return verdict_reason(
        saved_at=saved_at,
        now=NOW,
        stat=stat,
        forgotten_days=21,
        listened_tracks=4,
        listened_days=3,
    )


def test_forgotten_reason_reports_days() -> None:
    assert forgotten_reason(NOW - timedelta(days=30), NOW) == "30d"


def test_listened_by_track_count_takes_priority() -> None:
    stat = PlayStat(distinct_tracks=4, first_played=NOW, last_played=NOW)
    assert _reason(saved_days=30, stat=stat) == "4 plays"


def test_listened_by_day_span() -> None:
    stat = PlayStat(distinct_tracks=1, first_played=NOW - timedelta(days=4), last_played=NOW)
    assert _reason(saved_days=1, stat=stat) == "played over 4d"


def test_forgotten_fallback_when_not_listened() -> None:
    assert _reason(saved_days=30, stat=ZERO_PLAYS) == "30d"


def test_none_when_neither_fires() -> None:
    stat = PlayStat(distinct_tracks=1, first_played=NOW, last_played=NOW)
    assert _reason(saved_days=5, stat=stat) is None
