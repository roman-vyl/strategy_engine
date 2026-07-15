from __future__ import annotations

from strategy_engine.service.settings import Settings


def test_settings_are_environment_driven(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGY_ENGINE_HTTP_PORT", "9999")
    monkeypatch.setenv("STRATEGY_ENGINE_MDS_BASE_URL", "http://mds:8080")
    settings = Settings.from_env()
    assert settings.http_port == 9999
    assert settings.mds_base_url == "http://mds:8080"
