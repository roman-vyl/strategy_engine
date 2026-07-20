from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import (
    MarketStreamNotReadyError,
    TargetBarNotCommittedError,
    UpstreamContractError,
)
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange, timeframe_duration_ms
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.load_live_feature_frame import (
    LiveFeatureFrameRequest,
    LoadLiveFeatureFrame,
)
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import StrategySpecEnvelope
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


class FakeMarketData:
    def __init__(
        self,
        *,
        state: str = "ready",
        earliest: int | None = 0,
        latest: int | None = 3_300_000,
        final_bar_offset: int = 0,
    ) -> None:
        self.state = state
        self.earliest = earliest
        self.latest = latest
        self.final_bar_offset = final_bar_offset
        self.bounds_calls = 0
        self.range_calls = 0
        self.last_range: TimeRange | None = None

    def load_bounds(self, market: MarketStream) -> StreamBounds:
        self.bounds_calls += 1
        return StreamBounds(market, self.state, self.earliest, self.latest)

    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame:
        del expected_market_data_hash
        self.range_calls += 1
        self.last_range = time_range
        step = timeframe_duration_ms(market.base_timeframe)
        bars = []
        open_time = time_range.from_ms
        while open_time < time_range.to_ms + self.final_bar_offset:
            index = len(bars)
            bars.append(
                MarketBar(
                    open_time_ms=open_time,
                    open=Decimal(index + 1),
                    high=Decimal(index + 2),
                    low=Decimal(index),
                    close=Decimal(index + 1),
                    volume=Decimal("10"),
                )
            )
            open_time += step
        return MarketFrame(market, time_range, tuple(bars), "fixture-market-hash")


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


def build_loader(market_data: FakeMarketData) -> LoadLiveFeatureFrame:
    indicator_registry = IndicatorRegistry()
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    indicator_evaluator = EvaluateIndicatorRange(
        indicator_registry,
        market_data,
        validate_plan,
    )
    planner = BuildStrategyFeaturePlan()
    strategy_registry = StrategyRegistry(EmaPullbackRangeEvaluator(planner, indicator_evaluator))
    validator = ValidateStrategySpec(strategy_registry, planner)
    return LoadLiveFeatureFrame(market_data, planner, indicator_evaluator, validator)


def request(target: int = 3_300_000) -> LiveFeatureFrameRequest:
    return LiveFeatureFrameRequest(
        strategy=StrategySpecEnvelope(
            strategy_id="ema_pullback",
            strategy_version="v1",
            instance_id="fixture-live",
            raw_spec=minimal_spec(),
        ),
        market=MarketStream("BTCUSDT.P", "5m"),
        target_bar_open_time_ms=target,
    )


def test_live_frame_uses_earliest_bound_and_target_not_absolute_latest() -> None:
    market_data = FakeMarketData(latest=3_600_000)
    result = build_loader(market_data).execute(request(3_300_000))
    assert market_data.bounds_calls == 1
    assert market_data.range_calls == 1
    assert market_data.last_range == TimeRange(0, 3_600_000)
    assert result.target_index == 11
    assert result.frame.time_ms[-1] == 3_300_000
    assert result.market_data_hash == "fixture-market-hash"


def test_live_frame_rejects_non_ready_or_empty_bounds_without_candle_read() -> None:
    for market_data in (
        FakeMarketData(state="degraded"),
        FakeMarketData(earliest=None, latest=None),
    ):
        with pytest.raises(MarketStreamNotReadyError):
            build_loader(market_data).execute(request())
        assert market_data.range_calls == 0


def test_live_frame_rejects_target_outside_committed_bounds() -> None:
    market_data = FakeMarketData(latest=3_000_000)
    with pytest.raises(TargetBarNotCommittedError):
        build_loader(market_data).execute(request(3_300_000))
    assert market_data.range_calls == 0


def test_live_frame_rejects_incomplete_or_wrong_final_frame() -> None:
    class WrongFinalMarketData(FakeMarketData):
        def load_range(
            self,
            market: MarketStream,
            time_range: TimeRange,
            *,
            expected_market_data_hash: str | None = None,
        ) -> MarketFrame:
            frame = super().load_range(
                market,
                time_range,
                expected_market_data_hash=expected_market_data_hash,
            )
            return MarketFrame(
                market,
                time_range,
                frame.bars,
                frame.market_data_hash,
            )

    market_data = WrongFinalMarketData()
    result = build_loader(market_data).execute(request())
    assert result.frame.time_ms[-1] == 3_300_000

    # The existing bounded reader is the authoritative gap/incomplete guard.
    class BrokenMarketData(FakeMarketData):
        def load_range(
            self,
            market: MarketStream,
            time_range: TimeRange,
            *,
            expected_market_data_hash: str | None = None,
        ) -> MarketFrame:
            del expected_market_data_hash
            raise UpstreamContractError("bounds/candles race")

    with pytest.raises(UpstreamContractError):
        build_loader(BrokenMarketData()).execute(request())
