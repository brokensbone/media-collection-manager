from dataclasses import dataclass
from datetime import datetime


@dataclass
class PlayStat:
    distinct_tracks: int
    first_played: datetime | None
    last_played: datetime | None


ZERO_PLAYS = PlayStat(0, None, None)


def forgotten_reason(saved_at: datetime, now: datetime) -> str:
    days = (now - saved_at).days
    return f"{days}d"


def verdict_reason(
    *,
    saved_at: datetime | None,
    now: datetime,
    stat: PlayStat,
    forgotten_days: int,
    listened_tracks: int,
    listened_days: int,
) -> str | None:
    """Whether a saved album is ready to judge, and why (SPEC §6a). Two triggers:
    'listened' (enough distinct tracks, or plays spread over enough days) — preferred, more
    informative — and the time-based 'forgotten' fallback. None means not ready."""
    if stat.distinct_tracks >= listened_tracks:
        return f"{stat.distinct_tracks} plays"
    if stat.first_played and stat.last_played:
        span = (stat.last_played - stat.first_played).days
        if span >= listened_days:
            return f"played over {span}d"
    if saved_at is not None and (now - saved_at).days >= forgotten_days:
        return forgotten_reason(saved_at, now)
    return None
