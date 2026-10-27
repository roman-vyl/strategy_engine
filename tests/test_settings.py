from __future__ import annotations

from strategy_engine.service.settings import Settings


def test_settings_are_environment_driven(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGY_ENGINE_HTTP_PORT", "9999")
    monkeypatch.setenv("STRATEGY_ENGINE_MDS_BASE_URL", "http://mds:8080")
    settings = Settings.from_env()
    assert settings.http_port == 9999
    assert settings.mds_base_url == "http://mds:8080"


# -- engine config file (touch-signal-close-entry-v1) --------------------------

import pytest  # noqa: E402


def test_live_entry_mode_defaults_without_config(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("STRATEGY_ENGINE_CONFIG_PATH", raising=False)
    assert Settings.from_env().live_entry_mode == "ema_anchor"
    monkeypatch.setenv("STRATEGY_ENGINE_CONFIG_PATH", str(tmp_path / "missing.toml"))
    assert Settings.from_env().live_entry_mode == "ema_anchor"


@pytest.mark.parametrize("mode", ["ema_anchor", "touch_trigger"])
def test_live_entry_mode_from_config_file(monkeypatch, tmp_path, mode: str) -> None:
    path = tmp_path / "engine.toml"
    path.write_text(f'live_entry_mode = "{mode}"\n', encoding="utf-8")
    monkeypatch.setenv("STRATEGY_ENGINE_CONFIG_PATH", str(path))
    assert Settings.from_env().live_entry_mode == mode


def test_empty_config_file_keeps_defaults(monkeypatch, tmp_path) -> None:
    path = tmp_path / "engine.toml"
    path.write_text("# nothing set\n", encoding="utf-8")
    monkeypatch.setenv("STRATEGY_ENGINE_CONFIG_PATH", str(path))
    assert Settings.from_env().live_entry_mode == "ema_anchor"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('live_entry_mode = "close"\n', "live_entry_mode must be one of"),
        ('live_entry_mode = "touch_trigger"\nmode = 1\n', "unknown keys"),
        ("live_entry_mode = \n", "not valid TOML"),
    ],
)
def test_invalid_config_file_fails_start(monkeypatch, tmp_path, content: str, message: str) -> None:
    path = tmp_path / "engine.toml"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setenv("STRATEGY_ENGINE_CONFIG_PATH", str(path))
    with pytest.raises(ValueError, match=message):
        Settings.from_env()
