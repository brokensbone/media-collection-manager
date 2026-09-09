from dataclasses import dataclass
from datetime import datetime


@dataclass
class PlayStat:
    distinct_tracks: int
    first_played: datetime | None
    last_played: datetime | None


ZERO_PLAYS = PlayStat(0, None, None)


def listened_reason(*, stat: PlayStat, listened_tracks: int, listened_days: int) -> str:
    """A short 'you've actually heard this' hint for a Decide row (SPEC §6a), or '' when the
    album hasn't accrued enough plays. Two signals: enough distinct tracks, or plays spread
    over enough days. Purely informational — every saved album surfaces in Decide regardless;
    this only flags the ones that are an easy keep."""
    if stat.distinct_tracks >= listened_tracks:
        return f"{stat.distinct_tracks} plays"
    if stat.first_played and stat.last_played:
        span = (stat.last_played - stat.first_played).days
        if span >= listened_days:
            return f"played over {span}d"
    return ""
