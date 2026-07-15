from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.market import MarketBar, MarketFrame
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.evaluate_managed_replay import EvaluateManagedReplay
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


class FakeMarketData:
    def load_range(self, market, time_range):
        bars = tuple(
            MarketBar(
                i * 300_000,
                Decimal(str(100 + i)),
                Decimal(str(102 + i)),
                Decimal(str(99 + i)),
                Decimal(str(101 + i)),
                Decimal("1"),
            )
            for i in range(6)
        )
        return MarketFrame(market, time_range, bars, "fake-market-hash")

    def close(self) -> None:
        pass


def raw_spec() -> dict[str, object]:
    from tests.test_ema_pullback_managed import spec

    return spec()


def services() -> ApplicationServices:
    indicators = IndicatorRegistry()
    market_data = FakeMarketData()
    validate_plan = ValidateIndicatorPlan(indicators)
    indicator_eval = EvaluateIndicatorRange(indicators, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    strategy_evaluator = EmaPullbackRangeEvaluator(planner, indicator_eval)
    strategies = StrategyRegistry(strategy_evaluator)
    validate_strategy = ValidateStrategySpec(strategies, planner)
    range_eval = EvaluateStrategyRange(strategies, validate_strategy)
    return ApplicationServices(
        indicator_catalog=IndicatorCatalog(indicators),
        validate_indicator_plan=validate_plan,
        evaluate_indicator_range=indicator_eval,
        strategy_catalog=StrategyCatalog(strategies),
        validate_strategy_spec=validate_strategy,
        evaluate_strategy_range=range_eval,
        evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(range_eval),
        market_data_client=market_data,  # type: ignore[arg-type]
        evaluate_managed_replay=EvaluateManagedReplay(
            planner,
            indicator_eval,
            validate_strategy,
        ),
    )


def test_managed_replay_http_contract() -> None:
    with TestClient(create_app(services=services())) as client:
        response = client.post(
            "/v1/strategy-evaluations/managed-replay",
            json={
                "market": {
                    "ticker": "BTCUSDT.P",
                    "base_timeframe": "5m",
                    "from_ms": 0,
                    "to_ms": 1_800_000,
                },
                "strategy": {
                    "strategy_id": "ema_pullback",
                    "strategy_version": "v1",
                    "instance_id": "managed-1",
                    "raw_spec": raw_spec(),
                },
                "trade_id": "L1",
                "side": "long",
                "entry_time_ms": 0,
                "entry_price": 100.0,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "managed_policy_replay.v1"
    assert payload["decision_timing"] == "end_of_bar_effective_next_bar"
    assert payload["bars"][0]["effective_from_time_ms"] == 300000
    assert payload["bars"][-1]["effective_from_time_ms"] is None
    assert payload["final_state"]["phase"] == "exhaustion"
    assert payload["final_state"]["active_stop_price"] == "101.5"
    assert any(item["event_type"] == "runtime_exit_triggered" for item in payload["events"])
