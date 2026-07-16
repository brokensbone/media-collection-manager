import pytest

from wantlist.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.beets_command == "beet"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WANTLIST_BEETS_COMMAND", "docker exec beets beet")
    assert Settings().beets_command == "docker exec beets beet"
