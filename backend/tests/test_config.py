import pytest

from wantlist.config import Settings


def test_defaults() -> None:
    assert Settings().art_target_px == 300


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WANTLIST_ART_TARGET_PX", "500")
    assert Settings().art_target_px == 500
