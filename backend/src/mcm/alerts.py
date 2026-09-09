from .adapters.album_repo import AlbumRepo
from .ports.notifications import NotificationSender


class AlertsService:
    """Turns background state into operator nudges (§8d, D13): a want auto-resolving to
    owned, a triage backlog, and Spotify re-auth becoming due. Edge-triggered — each alert
    fires once per episode (dedup flags in the DB), not on every poll."""

    def __init__(self, *, notifier: NotificationSender, repo: AlbumRepo, triage_threshold: int):
        self._notifier = notifier
        self._repo = repo
        self._triage_threshold = triage_threshold

    def owned(self, newly_owned: int) -> None:
        if newly_owned > 0:
            self._notifier.send(f"{newly_owned} album(s) now owned.")

    def check(self, *, reauth_due: bool, decide_count: int) -> None:
        reauth_notified, triage_notified = self._repo.notification_flags()

        if reauth_due and not reauth_notified:
            self._notifier.send("Spotify needs reconnecting — reconnect so polling resumes.")
            self._repo.set_notification_flags(reauth_notified=True)
        elif not reauth_due and reauth_notified:
            self._repo.set_notification_flags(reauth_notified=False)  # re-arm after reconnect

        over = decide_count >= self._triage_threshold
        if over and not triage_notified:
            self._notifier.send(f"{decide_count} albums waiting for a verdict.")
            self._repo.set_notification_flags(triage_notified=True)
        elif not over and triage_notified:
            self._repo.set_notification_flags(triage_notified=False)  # re-arm once cleared
