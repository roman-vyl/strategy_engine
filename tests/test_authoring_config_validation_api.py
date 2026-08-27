from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.service.settings import Settings
from strategy_engine.service.wiring import build_services


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


def test_instance_strategy_id_matching_path_is_accepted() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [canonical_instance()]},
        )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_instance_strategy_id_not_matching_path_is_rejected() -> None:
    item = canonical_instance()
    item["strategy_id"] = "some_other_strategy"
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["details"]["path"] == "instances[0].strategy_id"
    assert body["details"]["path_strategy_id"] == "ema_pullback"
    assert body["details"]["instance_strategy_id"] == "some_other_strategy"


def test_mismatch_among_multiple_instances_identifies_offending_index() -> None:
    matching_a = canonical_instance()
    mismatched = canonical_instance()
    mismatched["strategy_id"] = "some_other_strategy"
    matching_b = canonical_instance()
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [matching_a, mismatched, matching_b]},
        )
    assert response.status_code == 422
    body = response.json()
    assert body["details"]["path"] == "instances[1].strategy_id"
    assert body["details"]["instance_strategy_id"] == "some_other_strategy"


def test_mismatch_is_caught_before_any_semantic_validation_call() -> None:
    # Boundary invariant: the path/body strategy_id check must reject the
    # whole request before ValidateStrategySpec.execute is ever invoked --
    # not be discovered indirectly via a downstream unknown-strategy error
    # from semantic validation.
    app_services = build_services(Settings())
    real_validate = app_services.validate_strategy_spec
    calls: list[object] = []

    class SpyValidateStrategySpec:
        def execute(self, strategy: object) -> str:
            calls.append(strategy)
            return real_validate.execute(strategy)  # type: ignore[arg-type]

    app_services.validate_strategy_spec = SpyValidateStrategySpec()  # type: ignore[assignment]

    matching_a = canonical_instance()
    mismatched = canonical_instance()
    mismatched["strategy_id"] = "some_other_strategy"
    with TestClient(create_app(services=app_services)) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [matching_a, mismatched]},
        )
    assert response.status_code == 422
    assert calls == []
