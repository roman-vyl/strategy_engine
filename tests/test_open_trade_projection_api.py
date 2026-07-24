from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.errors import TradeContractMismatchError
from strategy_engine.domain.market import MarketStream
from strategy_engine.strategies.application.evaluate_open_trade_projection import (
    EvaluateOpenTradeProjection,
)
from strategy_engine.strategies.contracts import (
    DesiredProtection,
    OpenTradeDiagnostics,
    OpenTradeProjectionResult,
    StrategicCloseSignal,
    StrategySpecEnvelope,
)
from tests.test_live_entry_projection_api import _services, _spec


def _strategy() -> StrategySpecEnvelope:
    return StrategySpecEnvelope(
        strategy_id="ema_pullback",
        strategy_version="v1",
        instance_id="live-1",
        raw_spec=_spec(),
        compatibility_profile="bbb_v1",
    )


def _payload() -> dict[str, object]:
    strategy = _strategy()
    return {
        "strategy": {
            "strategy_id": strategy.strategy_id,
            "strategy_version": strategy.strategy_version,
            "instance_id": strategy.instance_id,
            "raw_spec": strategy.raw_spec,
            "compatibility_profile": strategy.compatibility_profile,
        },
        "market": {"ticker": "BTCUSDT.P", "base_timeframe": "5m"},
        "target_bar_open_time_ms": 3_300_000,
        "executed_trade_receipt": {
            "trade_id": "trade-1",
            "instance_id": "live-1",
            "strategy_id": "ema_pullback",
            "strategy_version": "v1",
            "source_config_hash": strategy.config_hash,
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "side": "long",
            "source_plan_bar_open_time_ms": 2_700_000,
            "entry_bar_open_time_ms": 3_000_000,
            "planned_entry_price": "10",
            "executed_entry_price": "10.1",
            "initial_stop_price": "9.5",
            "initial_take_price": "11",
            "locked_exit_profile": "aligned",
            "abi_entry_correlation": "abi-entry-1",
        },
    }


def _managed_payload() -> dict[str, object]:
    payload = _payload()
    strategy = payload["strategy"]
    assert isinstance(strategy, dict)
    raw_spec = strategy["raw_spec"]
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
    strategy["raw_spec"] = raw_spec
    strategy_domain = StrategySpecEnvelope(
        strategy_id=strategy["strategy_id"],
        strategy_version=strategy["strategy_version"],
        instance_id=strategy["instance_id"],
        raw_spec=raw_spec,
        compatibility_profile=strategy["compatibility_profile"],
    )
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["source_config_hash"] = strategy_domain.config_hash
    return payload


def _result() -> OpenTradeProjectionResult:
    strategy = _strategy()
    return OpenTradeProjectionResult(
        trade_id="trade-1",
        instance_id="live-1",
        strategy_id="ema_pullback",
        strategy_version="v1",
        source_config_hash=strategy.config_hash,
        market=MarketStream("BTCUSDT.P", "5m"),
        target_bar_open_time_ms=3_300_000,
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
        "trade_id": "trade-1",
        "instance_id": "live-1",
        "strategy_id": "ema_pullback",
        "strategy_version": "v1",
        "source_config_hash": _strategy().config_hash,
        "market": {"ticker": "BTCUSDT.P", "base_timeframe": "5m"},
        "target_bar_open_time_ms": 3_300_000,
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
    assert body["trade_id"] == "trade-1"
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


def test_open_trade_http_preserves_typed_application_error() -> None:
    app_services, _ = _services()

    def fail(_request: object) -> object:
        raise TradeContractMismatchError(mismatches={"instance_id": "other"})

    app_services.evaluate_open_trade_projection = SimpleNamespace(execute=fail)
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=_payload())

    assert response.status_code == 409
    assert response.json()["error"] == "trade_contract_mismatch"
    assert response.json()["details"] == {"mismatches": {"instance_id": "other"}}
    assert isinstance(response.json()["request_id"], str)


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
    assert "market_data_hash" not in response_schema["properties"]
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
    strategy = payload["strategy"]
    assert isinstance(strategy, dict)
    raw_spec = strategy["raw_spec"]
    assert isinstance(raw_spec, dict)
    trade_management = raw_spec["trade_management"]
    assert isinstance(trade_management, dict)
    exit_management = trade_management["exit_management"]
    assert isinstance(exit_management, dict)
    if mode is None:
        exit_management.pop("mode", None)
    else:
        exit_management["mode"] = mode
    strategy_domain = StrategySpecEnvelope(
        strategy_id=strategy["strategy_id"],
        strategy_version=strategy["strategy_version"],
        instance_id=strategy["instance_id"],
        raw_spec=raw_spec,
        compatibility_profile=strategy["compatibility_profile"],
    )
    receipt = payload["executed_trade_receipt"]
    assert isinstance(receipt, dict)
    receipt["source_config_hash"] = strategy_domain.config_hash

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
    receipt["executed_entry_price"] = "10.123456789012345679"
    receipt["initial_stop_price"] = "9.1234567890123456789"
    receipt["initial_take_price"] = "11.1234567890123456789"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/open-trade", json=payload)

    assert response.status_code == 200
    assert response.json()["desired_protection"] == {
        "stop_price": "9.1234567890123456789",
        "take_price": "11.1234567890123456789",
    }
