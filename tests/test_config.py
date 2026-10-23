from app.config import (
    get_ai_analysis_delay,
    get_ai_settings,
    get_analysis_interval,
    get_analysis_max_attempts,
    get_analysis_window,
    get_auto_analysis,
    get_web_port,
    get_ws_port,
)


def test_default_interval_is_five_minutes(monkeypatch):
    monkeypatch.delenv("ANALYSIS_INTERVAL", raising=False)
    monkeypatch.delenv("AI_ANALYSIS_DELAY", raising=False)

    assert get_analysis_interval() == 300.0
    assert get_ai_analysis_delay() == 300.0


def test_interval_can_be_overridden(monkeypatch):
    monkeypatch.setenv("ANALYSIS_INTERVAL", "60")

    assert get_analysis_interval() == 60.0


def test_invalid_interval_falls_back(monkeypatch):
    monkeypatch.setenv("ANALYSIS_INTERVAL", "-5")

    assert get_analysis_interval() == 300.0


def test_legacy_delay_variable_still_works(monkeypatch):
    monkeypatch.delenv("ANALYSIS_INTERVAL", raising=False)
    monkeypatch.setenv("AI_ANALYSIS_DELAY", "10")

    assert get_analysis_interval() == 10.0


def test_ports_have_defaults(monkeypatch):
    monkeypatch.delenv("WEB_PORT", raising=False)
    monkeypatch.delenv("WS_PORT", raising=False)

    assert get_web_port() == 5000
    assert get_ws_port() == 8765


def test_window_and_attempts_have_defaults(monkeypatch):
    monkeypatch.delenv("ANALYSIS_WINDOW", raising=False)
    monkeypatch.delenv("ANALYSIS_MAX_ATTEMPTS", raising=False)

    assert get_analysis_window() == 100
    assert get_analysis_max_attempts() == 5


def test_auto_analysis_flag(monkeypatch):
    monkeypatch.setenv("AUTO_ANALYSIS", "0")
    assert get_auto_analysis() is False

    monkeypatch.setenv("AUTO_ANALYSIS", "1")
    assert get_auto_analysis() is True


def test_generic_ai_settings_win_over_legacy(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "new-key")
    monkeypatch.setenv("ZHIPU_API_KEY", "old-key")
    monkeypatch.setenv("AI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("AI_MODEL", "some-model")

    settings = get_ai_settings()

    assert settings["api_key"] == "new-key"
    assert settings["base_url"] == "https://example.com/v1"
    assert settings["model"] == "some-model"
