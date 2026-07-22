import pytest
from sqlalchemy.orm import Session, sessionmaker

import wantlist.adapters.event_log as event_log
from wantlist.adapters.event_log import WorkerEventLog


def test_emit_and_recent_are_ascending(clean_album_tables: sessionmaker[Session]) -> None:
    log = WorkerEventLog(clean_album_tables)
    log.emit(job="resolution", type="resolved", message="A")
    log.emit(job="reconcile", type="owned", message="B")
    rows = log.recent()
    assert [(r.job, r.type, r.message) for r in rows] == [
        ("resolution", "resolved", "A"),
        ("reconcile", "owned", "B"),
    ]


def test_recent_after_returns_only_newer(clean_album_tables: sessionmaker[Session]) -> None:
    log = WorkerEventLog(clean_album_tables)
    log.emit(job="j", type="t", message="one")
    cursor = log.recent()[0].id
    log.emit(job="j", type="t", message="two")
    assert [r.message for r in log.recent(after=cursor)] == ["two"]


def test_recent_without_cursor_returns_the_latest_page(
    clean_album_tables: sessionmaker[Session],
) -> None:
    log = WorkerEventLog(clean_album_tables)
    for i in range(5):
        log.emit(job="j", type="t", message=str(i))
    # latest 2, still ascending so the client can take the last id as its cursor
    assert [r.message for r in log.recent(limit=2)] == ["3", "4"]


def test_prunes_to_a_recent_window(
    clean_album_tables: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(event_log, "_KEEP", 5)
    monkeypatch.setattr(event_log, "_PRUNE_EVERY", 3)
    log = WorkerEventLog(clean_album_tables)
    for i in range(30):
        log.emit(job="j", type="t", message=str(i))
    # bounded around _KEEP (plus up to _PRUNE_EVERY of slack), never the full 30
    assert len(log.recent(limit=100)) <= 8
