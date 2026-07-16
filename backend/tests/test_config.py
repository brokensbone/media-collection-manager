import pytest

from wantlist.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.beets_config is None
    assert settings.art_target_px == 300


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WANTLIST_BEETS_CONFIG", "/etc/beets/config.yaml")
    assert Settings().beets_config == "/etc/beets/config.yaml"
