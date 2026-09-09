from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class AuthStatus:
    connected: bool
    authorized_at: datetime | None
    reauth_in_days: int | None
    reauth_due: bool


def compute_status(
    *,
    connected: bool,
    authorized_at: datetime | None,
    now: datetime,
    lifetime_days: int,
    warn_days: int,
) -> AuthStatus:
    """Pure re-auth countdown (SPEC §8c). Refresh tokens expire ~lifetime_days after
    the last authorization; warn when within warn_days of that."""
    if not connected or authorized_at is None:
        return AuthStatus(
            connected=False, authorized_at=authorized_at, reauth_in_days=None, reauth_due=True
        )
    expires_at = authorized_at + timedelta(days=lifetime_days)
    days = (expires_at - now).days
    return AuthStatus(
        connected=True,
        authorized_at=authorized_at,
        reauth_in_days=days,
        reauth_due=days <= warn_days,
    )
