from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.service.settings import Settings


def test_ema_pullback_composer_catalog_preserves_bbb_contract() -> None:
    client = TestClient(create_app(settings=Settings()))
    response = client.get("/v1/strategies/ema_pullback/composer-catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["family"] == "ema_pullback"
    assert body["schema_version"] == 1
    ids = {item["component_id"] for item in body["components"]}
    assert {"ema_anchor_stack_trend", "untouched_anchor_setup", "reclaim_anchor"} <= ids
    assert any(item["component_id"] == "htf_context" for item in body["context_providers"])


def test_unknown_strategy_composer_catalog_is_404() -> None:
    client = TestClient(create_app(settings=Settings()))
    response = client.get("/v1/strategies/unknown/composer-catalog")
    assert response.status_code == 404
