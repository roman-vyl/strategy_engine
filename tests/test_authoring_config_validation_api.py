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


def _atr_exit_rule(*, instance_id: str | None) -> dict[str, object]:
    rule: dict[str, object] = {
        "component_id": "atr_stop_loss",
        "exit_kind": "stop_loss",
        "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
    }
    if instance_id is not None:
        rule["instance_id"] = instance_id
    return rule


def test_atr_exit_rule_without_instance_id_is_rejected() -> None:
    item = canonical_instance()
    exit_policy = item["raw_spec"]["trade_management"]["exit_policy"]  # type: ignore[index]
    exit_policy["always_on"]["exits"] = [_atr_exit_rule(instance_id=None)]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["path"] == "instances[0]"


def test_atr_exit_rule_with_instance_id_is_accepted() -> None:
    item = canonical_instance()
    exit_policy = item["raw_spec"]["trade_management"]["exit_policy"]  # type: ignore[index]
    exit_policy["always_on"]["exits"] = [_atr_exit_rule(instance_id="atr_stop_1")]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


def _blocker(*, component_id: str = "no_blockers", instance_id: str | None = "blocker-1") -> dict:
    item: dict[str, object] = {"component_id": component_id}
    if instance_id is not None:
        item["instance_id"] = instance_id
    return item


def _setup(
    *, component_id: str = "untouched_anchor_setup", instance_id: str | None = "setup-1"
) -> dict:
    item: dict[str, object] = {"component_id": component_id}
    if instance_id is not None:
        item["instance_id"] = instance_id
    return item


def test_unsupported_blocker_component_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["blockers"] = [_blocker(component_id="does_not_exist")]  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_unsupported_trigger_component_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["trigger"] = {"component_id": "does_not_exist"}  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_unsupported_risk_component_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["risk"] = "does_not_exist"  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_unsupported_setup_component_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["setups"] = [_setup(component_id="does_not_exist")]  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_missing_blocker_instance_id_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["blockers"] = [_blocker(instance_id=None)]  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_missing_setup_instance_id_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["setups"] = [_setup(instance_id=None)]  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_duplicate_blocker_instance_id_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["blockers"] = [  # type: ignore[index]
        _blocker(instance_id="dup"),
        _blocker(instance_id="dup"),
    ]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_duplicate_setup_instance_id_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["setups"] = [  # type: ignore[index]
        _setup(instance_id="dup"),
        _setup(instance_id="dup"),
    ]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_duplicate_exit_instance_id_across_groups_is_rejected() -> None:
    # Old-BBB parity: uniqueness spans always_on + all three profiles
    # combined, not per-group.
    item = canonical_instance()
    exit_policy = item["raw_spec"]["trade_management"]["exit_policy"]  # type: ignore[index]
    exit_policy["always_on"]["exits"] = [_atr_exit_rule(instance_id="dup")]
    exit_policy["profiles"]["aligned"]["exits"] = [_atr_exit_rule(instance_id="dup")]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_malformed_trade_sides_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["trade_sides"] = ["not_a_side"]  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_non_object_blocker_entry_is_rejected() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["blockers"] = ["not_an_object"]  # type: ignore[index]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_fully_correct_canonical_spec_is_valid() -> None:
    item = canonical_instance()
    item["raw_spec"]["components"]["blockers"] = [_blocker(instance_id="blocker-1")]  # type: ignore[index]
    item["raw_spec"]["setups"] = [_setup(instance_id="setup-1")]  # type: ignore[index]
    exit_policy = item["raw_spec"]["trade_management"]["exit_policy"]  # type: ignore[index]
    exit_policy["always_on"]["exits"] = [_atr_exit_rule(instance_id="exit-1")]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_authoring_validation_does_not_accept_or_require_market_data() -> None:
    # Negative control: the request/response contract carries no market
    # data field at all -- authoring validation is a pure raw_spec check.
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [canonical_instance()]},
        )
    assert response.status_code == 200
    assert "market" not in response.json()
    assert response.json()["valid"] is True


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
