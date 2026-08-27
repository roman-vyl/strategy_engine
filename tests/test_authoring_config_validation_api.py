from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app


def raw_spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "components": {"blockers": []},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def canonical_instance(*, enabled: bool = True) -> dict[str, object]:
    return {
        "enabled": enabled,
        "strategy_id": "ema_pullback",
        "ticker": "BTCUSDT.P",
        "base_timeframe": "5m",
        "raw_spec": raw_spec(),
    }


def test_canonical_flat_instance_is_accepted() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [canonical_instance()]},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["instances"] == [{"index": 0, "config_hash": body["instances"][0]["config_hash"]}]
    assert "instance_id" not in body["instances"][0]


def test_enabled_true_and_false_validate_identically() -> None:
    with TestClient(create_app()) as client:
        enabled_response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [canonical_instance(enabled=True)]},
        )
        disabled_response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [canonical_instance(enabled=False)]},
        )
    assert enabled_response.status_code == disabled_response.status_code == 200
    assert enabled_response.json()["valid"] is disabled_response.json()["valid"] is True
    assert (
        enabled_response.json()["instances"][0]["config_hash"]
        == disabled_response.json()["instances"][0]["config_hash"]
    )


def test_returns_path_for_semantically_invalid_instance() -> None:
    item = canonical_instance()
    anchor_stack = item["raw_spec"]["anchor_stack"]  # type: ignore[index]
    anchor_stack["fast"]["period"] = 0
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["path"] == "instances[0]"


def test_legacy_instance_id_field_is_rejected() -> None:
    item = canonical_instance()
    item["instance_id"] = "legacy"
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 422


def test_legacy_market_field_is_rejected() -> None:
    item = canonical_instance()
    item["market"] = {"symbol": "BTCUSDT", "base_timeframe": "5m"}
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 422


def test_legacy_nested_strategy_field_is_rejected() -> None:
    item = canonical_instance()
    item["strategy"] = {"raw_spec": raw_spec()}
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 422
