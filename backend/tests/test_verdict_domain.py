from datetime import UTC, datetime, timedelta

from wantlist.domain.verdict import ZERO_PLAYS, PlayStat, listened_reason

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _reason(stat: PlayStat) -> str:
    return listened_reason(stat=stat, listened_tracks=4, listened_days=3)


def test_listened_by_track_count_takes_priority() -> None:
    stat = PlayStat(distinct_tracks=4, first_played=NOW, last_played=NOW)
    assert _reason(stat) == "4 plays"


def test_listened_by_day_span() -> None:
    stat = PlayStat(distinct_tracks=1, first_played=NOW - timedelta(days=4), last_played=NOW)
    assert _reason(stat) == "played over 4d"


def test_empty_when_not_listened_enough() -> None:
    stat = PlayStat(distinct_tracks=1, first_played=NOW, last_played=NOW)
    assert _reason(stat) == ""


def test_empty_for_zero_plays() -> None:
    assert _reason(ZERO_PLAYS) == ""
