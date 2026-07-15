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
            evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(strategy_eval),
            market_data_client=market_data,  # type: ignore[arg-type]
            build_strategy_feature_plan=planner,
        ),
        market_data,
    )


def payload(instance_id: str = "fixture") -> dict[str, object]:
    return {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 3_600_000,
        },
        "strategy": {
            "strategy_id": "ema_pullback",
            "strategy_version": "v1",
            "instance_id": instance_id,
            "raw_spec": minimal_spec(),
            "compatibility_profile": "bbb_v1",
        },
    }


def test_strategy_range_builds_plan_and_features_inside_service() -> None:
    app_services, market_data = services()
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/range", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "strategy_evaluation.v1"
    assert body["market"]["bar_count"] == 12
    assert body["market"]["market_data_hash"] == "fixture-market-hash"
    assert body["validity"]["stage"] == "decisions_ready"
    assert body["validity"]["contexts_ready"] is True
    assert body["validity"]["decisions_ready"] is True
    assert body["validity"]["entries_ready"] is True
    assert set(body["features"]["series"]) == {
        "ema_close_base_2",
        "ema_close_base_3",
        "ema_close_base_5",
    }
    assert body["features"]["mappings"]["anchor_columns"]["anchor"] == "ema_close_base_3"
    assert body["features"]["market_data_hash"] == "fixture-market-hash"
    assert body["contexts"]["items"]["trend"]["state"][-1] == "up"
    assert set(body["entries"]) == {"long", "short"}
    assert body["entries"]["short"] == [False] * 12
    assert body["validity"]["entries_ready"] is True
    evidence = body["component_evidence"]["direction_blockers"][0]
    assert evidence["direction"]["component_id"] == "ema_anchor_stack_trend"
    assert market_data.calls == 1


def test_strategy_catalog_advertises_feature_stage_not_decisions() -> None:
    app_services, _ = services()
    with TestClient(create_app(services=app_services)) as client:
        item = client.get("/v1/strategies").json()["items"][0]
    assert item["supports_range_evaluation"] is True
    assert item["evaluation_stage"] == "decisions_ready"
    assert item["supports_contexts"] is True
    assert item["supports_decisions"] is True
