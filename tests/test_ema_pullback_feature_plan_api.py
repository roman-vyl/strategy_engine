from __future__ import annotations

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from tests.test_ema_pullback_feature_plan import canonical_spec


def envelope() -> dict[str, object]:
    return {
        "strategy_id": "ema_pullback",
        "strategy_version": "v1",
        "instance_id": "fixture",
        "raw_spec": canonical_spec(),
        "compatibility_profile": "bbb_v1",
    }


def test_catalog_and_feature_plan_endpoint() -> None:
    with TestClient(create_app()) as client:
        items = client.get("/v1/strategies").json()["items"]
        assert items[0]["strategy_id"] == "ema_pullback"
        assert items[0]["supports_feature_planning"] is True
        assert items[0]["supports_range_evaluation"] is True
        response = client.post(
            "/v1/strategies/ema_pullback/feature-plan",
            json=envelope(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["anchor_columns"]["anchor"] == "ema_close_base_50"
        assert any(item["kind"] == "atr_distance" for item in body["features"])


def test_strategy_validation_now_validates_feature_discovery() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategies/ema_pullback/validate", json=envelope())
        assert response.status_code == 200
        assert response.json()["valid"] is True


def test_catalog_marks_standard_decisions_as_ported() -> None:
    with TestClient(create_app()) as client:
        item = client.get("/v1/strategies").json()["items"][0]
    assert item["evaluation_stage"] == "decisions_ready"
    assert item["supports_decisions"] is True
