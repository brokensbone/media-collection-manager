from datetime import datetime


def forgotten_reason(saved_at: datetime, now: datetime) -> str:
    """Why a saved album surfaced for a verdict (SPEC §6a). v1 has only the time-based
    'forgotten' trigger; the play-based 'listened' reason arrives with play-history (D8)."""
    days = (now - saved_at).days
    return f"saved {days}d ago"
