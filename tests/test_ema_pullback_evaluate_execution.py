from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import LiveStrategySpec, StrategyRangeRequest
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


class FakeMarketData:
    def load_range(self, market: MarketStream, time_range: TimeRange) -> MarketFrame:
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


def _minimal_spec() -> dict[str, object]:
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


def _evaluator() -> EmaPullbackRangeEvaluator:
    indicator_registry = IndicatorRegistry()
    market_data = FakeMarketData()
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    indicator_eval = EvaluateIndicatorRange(indicator_registry, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    return EmaPullbackRangeEvaluator(planner, indicator_eval)


def _request() -> StrategyRangeRequest:
    return StrategyRangeRequest(
        strategy=LiveStrategySpec(strategy_id="ema_pullback", raw_spec=_minimal_spec()),
        market=MarketStream(ticker="BTCUSDT.P", base_timeframe="5m"),
        time_range=TimeRange(from_ms=0, to_ms=3_600_000),
    )


def test_execution_contract_has_no_time_ms_or_diagnostic_fields() -> None:
    result = _evaluator().evaluate_execution(_request())
    field_names = {f for f in result.__dataclass_fields__}
    assert "time_ms" not in field_names
    assert "features" not in field_names
    assert "contexts" not in field_names
    assert "component_evidence" not in field_names
    assert "potential_entries" not in field_names


def test_execution_contract_provenance_matches_frame_not_features_dict() -> None:
    result = _evaluator().evaluate_execution(_request())
    assert result.market_data_hash == "fixture-market-hash"
    assert result.bar_count == 12


def test_execution_contract_decision_events_bar_index_within_bar_count() -> None:
    result = _evaluator().evaluate_execution(_request())
    for event in result.decision_events:
        assert 0 <= event.bar_index < result.bar_count


def test_diagnostic_evaluation_carries_dense_data_execution_contract_does_not() -> None:
    diagnostics = _evaluator().evaluate_diagnostics(_request())
    assert "series" in diagnostics.features
    assert diagnostics.market_data_hash == "fixture-market-hash"
    assert diagnostics.bar_count == 12


def test_execution_and_diagnostic_provenance_agree_for_the_same_request() -> None:
    request = _request()
    execution = _evaluator().evaluate_execution(request)
    diagnostics = _evaluator().evaluate_diagnostics(request)
    assert execution.market_data_hash == diagnostics.market_data_hash
    assert execution.bar_count == diagnostics.bar_count
    assert execution.config_hash == diagnostics.config_hash
