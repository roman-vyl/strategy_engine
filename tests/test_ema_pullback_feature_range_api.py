from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


class FakeMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def load_range(self, market: MarketStream, time_range: TimeRange) -> MarketFrame:
        self.calls += 1
        bars = tuple(
            MarketBar(
                index * 300_000,
                Decimal(str(index + 1)),
                Decimal(str(index + 2)),
                Decimal(str(index)),
                Decimal(str(index + 1)),
                Decimal("10"),
            )
            for index in range(12)
        )
        return MarketFrame(market, time_range, bars, "fixture-market-hash")

    def close(self) -> None:
        pass


def minimal_spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "components": {"blockers": []},
        "setups": [],
        "contexts": {
            "trend": {
                "component_id": "htf_context",
                "timeframe": "base",
                "source": "close",
                "fast_period": 2,
                "anchor_period": 3,
                "slow_period": 5,
            }
        },
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


def services() -> tuple[ApplicationServices, FakeMarketData]:
    indicator_registry = IndicatorRegistry()
    market_data = FakeMarketData()
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    indicator_eval = EvaluateIndicatorRange(indicator_registry, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    strategy_impl = EmaPullbackRangeEvaluator(planner, indicator_eval)
    strategy_registry = StrategyRegistry(strategy_impl)
    validate_strategy = ValidateStrategySpec(strategy_registry, planner)
    strategy_eval = EvaluateStrategyRange(strategy_registry, validate_strategy)
    return (
        ApplicationServices(
            indicator_catalog=IndicatorCatalog(indicator_registry),
            validate_indicator_plan=validate_plan,
            evaluate_indicator_range=indicator_eval,
            strategy_catalog=StrategyCatalog(strategy_registry),
            validate_strategy_spec=validate_strategy,
            evaluate_strategy_range=strategy_eval,
            evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(strategy_eval, market_data),
            market_data_client=market_data,  # type: ignore[arg-type]
            build_strategy_feature_plan=planner,
        ),
        market_data,
    )


def payload() -> dict[str, object]:
    return {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 3_600_000,
        },
        "strategy": {
            "strategy_id": "ema_pullback",
            "raw_spec": minimal_spec(),
        },
    }


def test_strategy_range_builds_plan_inside_service() -> None:
    # compact-strategy-evaluation-boundary-v1: /range now returns the
    # sparse mandatory execution contract only -- no dense
    # features/contexts/entries/component_evidence/validity. Dense-
    # content assertions moved to
    # test_strategy_range_diagnostics_builds_plan_and_features below,
    # against the separate diagnostics route.
    app_services, market_data = services()
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/range", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "strategy_evaluation_execution.v1"
    assert body["market"]["bar_count"] == 12
    assert body["market"]["market_data_hash"] == "fixture-market-hash"
    assert len(body["decision_events"]) == 12
    assert all(0 <= event["bar_index"] < 12 for event in body["decision_events"])
    # matches the pre-cutover contract's guarantee for this fixture:
    # entries["short"] == [False] * 12 -- no event ever carries a short entry.
    assert all(
        event["entry"] is None or event["entry"]["side"] == "long"
        for event in body["decision_events"]
    )
    assert market_data.calls == 1


def test_range_response_exact_key_set() -> None:
    # Authoritative reference for exactly what a successful /range
    # response top level looks like now: the sparse execution contract
    # (compact-strategy-evaluation-boundary-v1) -- no dense
    # features/contexts/entries/potential_entries/exit_policy/
    # component_evidence/validity/state_artifact.
    app_services, _ = services()
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/range", json=payload())
    assert response.status_code == 200
    assert set(response.json()) == {
        "contract_version",
        "strategy_id",
        "config_hash",
        "market",
        "decision_events",
        "warnings",
    }


def test_strategy_range_diagnostics_builds_plan_and_features() -> None:
    app_services, market_data = services()
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/range/diagnostics", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "strategy_diagnostic_evaluation.v1"
    assert body["market"]["bar_count"] == 12
    assert body["market"]["market_data_hash"] == "fixture-market-hash"
    assert set(body["features"]["series"]) == {
        "ema_close_base_2",
        "ema_close_base_3",
        "ema_close_base_5",
    }
    assert body["features"]["mappings"]["anchor_columns"]["anchor"] == "ema_close_base_3"
    assert body["features"]["market_data_hash"] == "fixture-market-hash"
    assert body["contexts"]["items"]["trend"]["state"][-1] == "up"
    assert body["potential_entries"] == {}
    evidence = body["component_evidence"]["direction_blockers"][0]
    assert evidence["direction"]["component_id"] == "ema_anchor_stack_trend"
    assert market_data.calls == 1


def test_diagnostics_response_exact_key_set() -> None:
    app_services, _ = services()
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/range/diagnostics", json=payload())
    assert response.status_code == 200
    assert set(response.json()) == {
        "contract_version",
        "strategy_id",
        "config_hash",
        "market",
        "features",
        "contexts",
        "potential_entries",
        "component_evidence",
        "warnings",
    }


def test_touch_anchor_range_adds_enabled_side_potential_prices_without_recalculation() -> None:
    app_services, market_data = services()
    request = payload()
    strategy = request["strategy"]
    assert isinstance(strategy, dict)
    spec = strategy["raw_spec"]
    assert isinstance(spec, dict)
    spec["trade_sides"] = {"enabled": ["long"]}
    components = spec["components"]
    assert isinstance(components, dict)
    components["trigger"] = {"component_id": "touch_anchor"}
    management = spec["trade_management"]
    assert isinstance(management, dict)
    policy = management["exit_policy"]
    assert isinstance(policy, dict)
    always_on = policy["always_on"]
    assert isinstance(always_on, dict)
    always_on["exits"] = [
        {
            "instance_id": "initial-stop",
            "component_id": "constant_usd_stop_loss",
            "exit_kind": "stop_loss",
            "usd_distance": 0.25,
        },
        {
            "instance_id": "initial-take",
            "component_id": "constant_usd_take_profit",
            "exit_kind": "take_profit",
            "usd_distance": 0.5,
        },
    ]

    with TestClient(create_app(services=app_services)) as client:
        execution_response = client.post("/v1/strategy-evaluations/range", json=request)
        diagnostics_response = client.post(
            "/v1/strategy-evaluations/range/diagnostics", json=request
        )

    assert execution_response.status_code == 200
    assert diagnostics_response.status_code == 200
    execution_body = execution_response.json()
    diagnostics_body = diagnostics_response.json()

    assert set(diagnostics_body["potential_entries"]) == {"long"}
    projected = diagnostics_body["potential_entries"]["long"]
    assert set(projected) == {"entry_price", "stop_price", "take_price"}
    assert all(len(projected[key]) == 12 for key in projected)
    assert all(
        all(value is None for value in triple) or all(value is not None for value in triple)
        for triple in zip(
            projected["entry_price"],
            projected["stop_price"],
            projected["take_price"],
            strict=True,
        )
    )
    long_entry_bar_indices = {
        event["bar_index"]
        for event in execution_body["decision_events"]
        if event["entry"] is not None and event["entry"]["side"] == "long"
    }
    assert any(
        bar_index in long_entry_bar_indices and projected["entry_price"][bar_index] is not None
        for bar_index in range(12)
    )
    # market data acquired once per request -- two requests here, two calls.
    assert market_data.calls == 2


def test_strategy_catalog_advertises_feature_stage_not_decisions() -> None:
    app_services, _ = services()
    with TestClient(create_app(services=app_services)) as client:
        item = client.get("/v1/strategies").json()["items"][0]
    assert item["supports_range_evaluation"] is True
    assert item["evaluation_stage"] == "decisions_ready"
    assert item["supports_contexts"] is True
    assert item["supports_decisions"] is True
