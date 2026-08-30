"""Regression tests for compact-strategy-evaluation-boundary-v1's
internal-only native fast path (task 3.3, Variant 3):

- strategy execution/diagnostic computation never boxes indicator values
  to normalized-decimal-text as an intermediate representation;
- the public indicator wire contract (serialize_value boxing) is
  unchanged and still exercised by the legacy/diagnostic paths;
- native and boxed computation are not two independent formula
  implementations -- they must agree numerically for the same input.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import strategy_engine.indicators.implementations.range_evaluator as range_evaluator_module
import strategy_engine.strategies.ema_pullback.evaluator as ema_pullback_evaluator_module
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


def _spy_serialize_value(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch serialize_value at every call site that could invoke it and
    record every call -- proves whether a code path boxes values."""

    calls: list[float] = []
    original = range_evaluator_module.serialize_value

    def spy(value: float) -> str | None:
        calls.append(value)
        return original(value)

    monkeypatch.setattr(range_evaluator_module, "serialize_value", spy)
    monkeypatch.setattr(ema_pullback_evaluator_module, "serialize_value", spy)
    return calls


def test_evaluate_execution_never_calls_serialize_value(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _spy_serialize_value(monkeypatch)
    _evaluator().evaluate_execution(_request())
    assert calls == []


def test_evaluate_diagnostics_boxes_only_at_the_output_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _spy_serialize_value(monkeypatch)
    diagnostics = _evaluator().evaluate_diagnostics(_request())
    # Positive control: this test would fail to catch a regression if
    # serialize_value were never called anywhere -- it IS still called
    # here, at the diagnostic wire boundary, proving the spy is live.
    assert len(calls) > 0
    boxed_series = diagnostics.features["series"]
    assert all(
        isinstance(value, str) or value is None
        for values in boxed_series.values()
        for value in values
    )


def test_legacy_evaluate_still_boxes_features_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _spy_serialize_value(monkeypatch)
    result = _evaluator().evaluate(_request())
    assert len(calls) > 0
    assert all(
        isinstance(value, str) or value is None
        for values in result.features["series"].values()
        for value in values
    )


def test_native_and_boxed_computation_agree_numerically() -> None:
    """Guards against native and public paths silently diverging into
    two independent formula implementations: parse the boxed public
    values back to float and compare exactly against the native path's
    own values, bar for bar, series for series."""

    request = _request()
    native = _evaluator().evaluate_execution(request)
    legacy = _evaluator()._evaluate_frame(request)[0]  # boxed FeatureFrame

    # The native path emits sparse decision events only, so agreement is
    # verified one level down: at the shared RangeIndicatorEvaluator,
    # native vs boxed-then-reparsed must be bitwise identical.
    indicator_registry = IndicatorRegistry()
    planner = BuildStrategyFeaturePlan()
    planned = planner.execute(request.strategy)
    market_frame = FakeMarketData().load_range(request.market, request.time_range)
    evaluator = indicator_registry.evaluator()
    assert evaluator is not None
    native_frame = evaluator.evaluate_native(market_frame, planned.indicator_plan)
    boxed_frame = evaluator.evaluate(market_frame, planned.indicator_plan)

    assert set(native_frame.series) == set(boxed_frame.series)
    for output_id, native_values in native_frame.series.items():
        boxed_values = boxed_frame.series[output_id]
        reparsed = tuple(None if v is None else float(v) for v in boxed_values)
        assert native_values == reparsed

    assert native.market_data_hash == legacy.market_data_hash
    assert native.bar_count == len(legacy.time_ms)
