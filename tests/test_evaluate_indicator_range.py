from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import EvaluationInvariantError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.indicators.contracts import (
    IndicatorPlan,
    IndicatorRangeRequest,
    PlannedFeature,
)
from strategy_engine.service.registries import IndicatorRegistry


class SpyMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def load_range(self, market: MarketStream, time_range: TimeRange, **_: object) -> MarketFrame:
        self.calls += 1
        return _frame(market, time_range)


def _frame(market: MarketStream, time_range: TimeRange, *, hash_suffix: str = "") -> MarketFrame:
    count = (time_range.to_ms - time_range.from_ms) // 300_000
    bars = tuple(
        MarketBar(
            time_range.from_ms + index * 300_000,
            Decimal(str(index + 1)),
            Decimal(str(index + 2)),
            Decimal(str(index)),
            Decimal(str(index + 1)),
            Decimal("10"),
        )
        for index in range(count)
    )
    return MarketFrame(market, time_range, bars, f"fixture-hash{hash_suffix}")


def _plan() -> IndicatorPlan:
    return IndicatorPlan(
        plan_version="v1",
        features=(PlannedFeature("ema_close_base_2", "ema", "base", "close", {"period": 2}),),
    )


def _build() -> tuple[EvaluateIndicatorRange, SpyMarketData]:
    registry = IndicatorRegistry()
    market_data = SpyMarketData()
    validator = ValidateIndicatorPlan(registry)
    return EvaluateIndicatorRange(registry, market_data, validator), market_data


def test_preloaded_frame_with_matching_identity_is_used_without_fetching() -> None:
    evaluator, market_data = _build()
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 1_500_000)
    frame = _frame(market, time_range)
    result = evaluator.execute(
        IndicatorRangeRequest(
            market=market, time_range=time_range, plan=_plan(), market_frame=frame
        )
    )
    assert market_data.calls == 0
    assert result.market_data_hash == "fixture-hash"


def test_preloaded_frame_with_different_market_is_rejected() -> None:
    evaluator, market_data = _build()
    request_market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 1_500_000)
    mismatched_frame = _frame(MarketStream("ETHUSDT.P", "5m"), time_range)
    with pytest.raises(EvaluationInvariantError):
        evaluator.execute(
            IndicatorRangeRequest(
                market=request_market,
                time_range=time_range,
                plan=_plan(),
                market_frame=mismatched_frame,
            )
        )
    assert market_data.calls == 0


def test_preloaded_frame_with_different_time_range_is_rejected() -> None:
    evaluator, market_data = _build()
    market = MarketStream("BTCUSDT.P", "5m")
    mismatched_frame = _frame(market, TimeRange(300_000, 1_800_000))
    with pytest.raises(EvaluationInvariantError):
        evaluator.execute(
            IndicatorRangeRequest(
                market=market,
                time_range=TimeRange(0, 1_500_000),
                plan=_plan(),
                market_frame=mismatched_frame,
            )
        )
    assert market_data.calls == 0


def test_preloaded_frame_with_mismatched_expected_hash_is_rejected() -> None:
    evaluator, market_data = _build()
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 1_500_000)
    frame = _frame(market, time_range)
    with pytest.raises(EvaluationInvariantError):
        evaluator.execute(
            IndicatorRangeRequest(
                market=market,
                time_range=time_range,
                plan=_plan(),
                expected_market_data_hash="some-other-hash",
                market_frame=frame,
            )
        )
    assert market_data.calls == 0


def test_no_preloaded_frame_still_fetches_as_today() -> None:
    evaluator, market_data = _build()
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 1_500_000)
    evaluator.execute(IndicatorRangeRequest(market=market, time_range=time_range, plan=_plan()))
    assert market_data.calls == 1
