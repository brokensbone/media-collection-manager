from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.alerts import AlertsService


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)


def _svc(sf: sessionmaker[Session], notifier: RecordingNotifier) -> AlertsService:
    return AlertsService(notifier=notifier, repo=AlbumRepo(sf), triage_threshold=10)  # type: ignore[arg-type]


def test_owned_notifies_only_when_positive(clean_album_tables: sessionmaker[Session]) -> None:
    notifier = RecordingNotifier()
    svc = _svc(clean_album_tables, notifier)
    svc.owned(0)
    assert notifier.messages == []
    svc.owned(3)
    assert notifier.messages == ["3 album(s) now owned."]


def test_reauth_fires_once_then_rearms(clean_album_tables: sessionmaker[Session]) -> None:
    notifier = RecordingNotifier()
    svc = _svc(clean_album_tables, notifier)
    svc.check(reauth_due=True, decide_count=0)
    svc.check(reauth_due=True, decide_count=0)  # still due → no repeat
    assert len(notifier.messages) == 1
    svc.check(reauth_due=False, decide_count=0)  # reconnected → re-arm
    svc.check(reauth_due=True, decide_count=0)  # due again → fires again
    assert len(notifier.messages) == 2


def test_triage_fires_on_threshold_and_rearms(
    clean_album_tables: sessionmaker[Session],
) -> None:
    notifier = RecordingNotifier()
    svc = _svc(clean_album_tables, notifier)
    svc.check(reauth_due=False, decide_count=9)  # below threshold
    assert notifier.messages == []
    svc.check(reauth_due=False, decide_count=10)  # crosses → fires
    svc.check(reauth_due=False, decide_count=15)  # still over → no repeat
    assert notifier.messages == ["10 albums waiting for a verdict."]
    svc.check(reauth_due=False, decide_count=2)  # cleared → re-arm
    svc.check(reauth_due=False, decide_count=12)  # over again → fires
    assert len(notifier.messages) == 2
