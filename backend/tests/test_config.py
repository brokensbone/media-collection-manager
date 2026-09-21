import pytest

from mcm.config import Settings


def test_defaults() -> None:
    assert Settings().art_target_px == 300


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCM_ART_TARGET_PX", "500")
    assert Settings().art_target_px == 500


def test_telegram_worklist_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCM_TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("MCM_TELEGRAM_WORKLIST_CHAT_IDS", "-100123, 456")
    settings = Settings()
    assert settings.telegram_bot_token == "secret-token"
    assert settings.telegram_worklist_chat_ids == "-100123, 456"
