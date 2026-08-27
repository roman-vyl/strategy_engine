from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.strategies.application.evaluate_open_trade_projection import (
    EvaluateOpenTradeProjection,
)
from strategy_engine.strategies.contracts import (
    DesiredProtection,
    LiveStrategySpec,
    OpenTradeDiagnostics,
    OpenTradeProjectionResult,
    StrategicCloseSignal,
)
from tests.test_live_entry_projection_api import _services, _spec


def _strategy() -> LiveStrategySpec:
    return LiveStrategySpec(
        strategy_id="ema_pullback",
        raw_spec=_spec(),
    )


def _payload() -> dict[str, object]:
    strategy = _strategy()
    return {
        "strategy_id": strategy.strategy_id,
        "raw_spec": strategy.raw_spec,
        "ticker": "BTCUSDT.P",
        "base_timeframe": "5m",
        "target_bar_open_time_ms": 3_300_000,
        "executed_trade_receipt": {
            "side": "long",
            "source_plan_bar_open_time_ms": 2_700_000,
            "entry_bar_open_time_ms": 3_000_000,
            "planned_entry_price": "10",
            "initial_stop_price": "9.5",
            "initial_take_price": "11",
            "locked_exit_profile": "aligned",
        },
    }


def _managed_payload() -> dict[str, object]:
    payload = _payload()
    raw_spec = payload["raw_spec"]
    assert isinstance(raw_spec, dict)
    trade_management = raw_spec["trade_management"]
    assert isinstance(trade_management, dict)
    trade_management["exit_management"] = {
        "mode": "managed",
        "phase_rules": [],
        "stop_management": [],
        "take_management": [],
        "runtime_exits": [],
    }
    payload["raw_spec"] = raw_spec
    return payload


def _result() -> OpenTradeProjectionResult:
    return OpenTradeProjectionResult(
        desired_protection=DesiredProtection(stop_price="10.25", take_price=None),
        close_signal=StrategicCloseSignal(
            active=True,
            reason="signal:aligned-exit",
            component_id="rsi_signal_exit",
            layer="exit_policy",
        ),
        diagnostics=OpenTradeDiagnostics(
            phase="protected",
            max_phase_reached="protected",
            bars_in_trade=2,
            mfe_pct="0.05",
            mae_pct="0.01",
            managed_events=({"event_type": "phase_changed", "bar_index": 11},),
        ),
    )


def test_open_trade_http_returns_typed_desired_state() -> None:
    app_services, _ = _services()
    app_services.evaluate_open_trade_projection = SimpleNamespace(
        execute=lambda _request: _result()
    )
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=_managed_payload())

    assert response.status_code == 200
    assert response.json() == {
        "desired_protection": {"stop_price": "10.25", "take_price": None},
        "close_signal": {
            "active": True,
            "reason": "signal:aligned-exit",
            "component_id": "rsi_signal_exit",
            "layer": "exit_policy",
        },
        "diagnostics": {
            "phase": "protected",
            "max_phase_reached": "protected",
            "bars_in_trade": 2,
            "mfe_pct": "0.05",
            "mae_pct": "0.01",
            "managed_events": [{"event_type": "phase_changed", "bar_index": 11}],
        },
    }


def test_open_trade_http_rejects_removed_instance_id() -> None:
    app_services, market_data = _services()
    payload = _payload()
    payload["instance_id"] = "live-1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_old_nested_payload() -> None:
    app_services, market_data = _services()
    flat = _payload()
    payload = {
        "strategy": {
            "strategy_id": flat["strategy_id"],
            "raw_spec": flat["raw_spec"],
        },
        "market": {
            "ticker": flat["ticker"],
            "base_timeframe": flat["base_timeframe"],
        },
        "target_bar_open_time_ms": flat["target_bar_open_time_ms"],
        "executed_trade_receipt": flat["executed_trade_receipt"],
    }

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_wires_real_application_use_case() -> None:
    app_services, market_data = _services()
    assert app_services.load_live_feature_frame is not None
    app_services.evaluate_open_trade_projection = EvaluateOpenTradeProjection(
        app_services.load_live_feature_frame
    )
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=_managed_payload())

    assert response.status_code == 200
    body = response.json()
    assert "contract_version" not in body
    assert "trade_id" not in body
    assert "market_data_hash" not in body
    assert body["desired_protection"]["stop_price"] == "9.5"
    assert market_data.bounds_calls == 1
    assert market_data.range_calls == 1


def test_open_trade_http_rejects_runtime_owned_state_fields() -> None:
    app_services, market_data = _services()
    app_services.evaluate_open_trade_projection = SimpleNamespace(
        execute=lambda _request: _result()
    )
    request = _payload()
    request["previous_managed_state"] = {"phase": "protected"}
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=request)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_removed_source_config_hash() -> None:
    app_services, market_data = _services()
    payload = _payload()
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["source_config_hash"] = "0" * 64

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_removed_abi_entry_correlation() -> None:
    app_services, market_data = _services()
    payload = _payload()
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["abi_entry_correlation"] = "abi-entry-1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_removed_trade_id() -> None:
    app_services, market_data = _services()
    payload = _payload()
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["trade_id"] = "trade-1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_removed_executed_entry_price() -> None:
    app_services, market_data = _services()
    payload = _payload()
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["executed_entry_price"] = "10.1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_removed_compatibility_profile() -> None:
    app_services, market_data = _services()
    payload = _payload()
    payload["compatibility_profile"] = "bbb_v1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_rejects_removed_strategy_version() -> None:
    app_services, market_data = _services()
    payload = _payload()
    payload["strategy_version"] = "v1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strategy_id", "ema_pullback"),
        ("instance_id", "live-1"),
        ("ticker", "BTCUSDT.P"),
        ("base_timeframe", "5m"),
    ],
)
def test_open_trade_http_rejects_removed_receipt_echo(
    field: str, value: str
) -> None:
    app_services, market_data = _services()
    payload = _payload()
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt[field] = value

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_open_trade_http_identical_retry_is_deterministic() -> None:
    app_services, _ = _services()
    app_services.evaluate_open_trade_projection = SimpleNamespace(
        execute=lambda _request: _result()
    )
    with TestClient(create_app(services=app_services)) as client:
        first = client.post("/v1/strategy-evaluations/open-trade", json=_payload())
        second = client.post("/v1/strategy-evaluations/open-trade", json=_payload())

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_open_trade_openapi_publishes_success_and_error_contracts() -> None:
    app_services, _ = _services()
    app_services.evaluate_open_trade_projection = SimpleNamespace(
        execute=lambda _request: _result()
    )
    with TestClient(create_app(services=app_services)) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/strategy-evaluations/open-trade"]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/OpenTradeProjectionRequestModel")
    assert response_ref.endswith("/OpenTradeProjectionResponseModel")
    response_schema = schema["components"]["schemas"]["OpenTradeProjectionResponseModel"]
    receipt_schema = schema["components"]["schemas"]["ExecutedTradeReceiptModel"]
    request_schema = schema["components"]["schemas"]["OpenTradeProjectionRequestModel"]
    assert set(request_schema["properties"]) == {
        "strategy_id",
        "raw_spec",
        "ticker",
        "base_timeframe",
        "target_bar_open_time_ms",
        "executed_trade_receipt",
    }
    # LiveStrategySpecModel is the canonical strategy-input model shared
    # across range/range-batch/managed-replay/validate/feature-plan -- it
    # legitimately appears in the app's schema components (from those other
    # endpoints), just not referenced by open-trade's own flat request model
    # (asserted above). LiveMarketModel has no other user and stays retired.
    assert "LiveMarketModel" not in schema["components"]["schemas"]
    assert "strategy_version" not in receipt_schema["properties"]
    assert "strategy_version" not in response_schema["properties"]
    for removed_echo in ("strategy_id", "instance_id", "ticker", "base_timeframe"):
        assert removed_echo not in receipt_schema["properties"]
    assert "trade_id" not in receipt_schema["properties"]
    assert "trade_id" not in response_schema["properties"]
    assert "abi_entry_correlation" not in receipt_schema["properties"]
    assert "source_config_hash" not in receipt_schema["properties"]
    assert "source_config_hash" not in response_schema["properties"]
    assert "market_data_hash" not in response_schema["properties"]
    assert set(response_schema["properties"]) == {
        "desired_protection",
        "close_signal",
        "diagnostics",
    }
    for status in ("404", "409", "422", "501", "502", "503", "500"):
        error_ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
        assert error_ref.endswith("/ErrorResponseModel")


def test_live_projection_openapi_declares_market_stream_not_found() -> None:
    app_services, _ = _services()
    schema = create_app(services=app_services).openapi()
    for path in (
        "/v1/strategy-evaluations/live-entry",
        "/v1/strategy-evaluations/open-trade",
    ):
        assert "404" in schema["paths"][path]["post"]["responses"]


@pytest.mark.parametrize("mode", [None, "diagnostic_only", "managed"])
def test_open_trade_real_path_accepts_all_live_management_modes(mode: str | None) -> None:
    app_services, _ = _services()
    assert app_services.load_live_feature_frame is not None
    app_services.evaluate_open_trade_projection = EvaluateOpenTradeProjection(
        app_services.load_live_feature_frame
    )
    payload = _managed_payload()
    raw_spec = payload["raw_spec"]
    assert isinstance(raw_spec, dict)
    trade_management = raw_spec["trade_management"]
    assert isinstance(trade_management, dict)
    exit_management = trade_management["exit_management"]
    assert isinstance(exit_management, dict)
    if mode is None:
        exit_management.pop("mode", None)
    else:
        exit_management["mode"] = mode
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 200
    assert response.json()["desired_protection"] == {
        "stop_price": "9.5",
        "take_price": "11",
    }


def test_open_trade_real_path_preserves_high_precision_receipt_protection() -> None:
    app_services, _ = _services()
    assert app_services.load_live_feature_frame is not None
    app_services.evaluate_open_trade_projection = EvaluateOpenTradeProjection(
        app_services.load_live_feature_frame
    )
    payload = _managed_payload()
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["planned_entry_price"] = "10.1234567890123456789"
    receipt["initial_stop_price"] = "9.1234567890123456789"
    receipt["initial_take_price"] = "11.1234567890123456789"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 200
    assert response.json()["desired_protection"] == {
        "stop_price": "9.1234567890123456789",
        "take_price": "11.1234567890123456789",
    }
