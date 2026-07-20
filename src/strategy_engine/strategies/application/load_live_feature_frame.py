"""Shared target-oriented live FeatureFrame acquisition."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_engine.domain.errors import (
    InvalidRequestError,
    MarketStreamNotReadyError,
    TargetBarNotCommittedError,
    UpstreamContractError,
)
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange, timeframe_duration_ms
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.contracts import FeatureFrame, IndicatorRangeRequest
from strategy_engine.ports.market_data import MarketDataPort
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import StrategySpecEnvelope
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan


@dataclass(frozen=True, slots=True)
class LiveFeatureFrameRequest:
    strategy: StrategySpecEnvelope
    market: MarketStream
    target_bar_open_time_ms: int


@dataclass(frozen=True, slots=True)
class LiveFeatureFrameBundle:
    strategy: StrategySpecEnvelope
    market: MarketStream
    target_bar_open_time_ms: int
    target_index: int
    bounds: StreamBounds
    requested_range: TimeRange
    planned_features: EmaPullbackFeaturePlan
    frame: FeatureFrame

    @property
    def market_data_hash(self) -> str:
        return self.frame.market_data_hash


class LoadLiveFeatureFrame:
    """Build one strategy-owned FeatureFrame from MDS ready bounds through target."""

    def __init__(
        self,
        market_data: MarketDataPort,
        feature_planner: BuildStrategyFeaturePlan,
        indicator_evaluator: EvaluateIndicatorRange,
        strategy_validator: ValidateStrategySpec,
    ) -> None:
        self._market_data = market_data
        self._feature_planner = feature_planner
        self._indicator_evaluator = indicator_evaluator
        self._strategy_validator = strategy_validator

    def execute(self, request: LiveFeatureFrameRequest) -> LiveFeatureFrameBundle:
        step_ms = timeframe_duration_ms(request.market.base_timeframe)
        target = request.target_bar_open_time_ms
        if target < 0 or target % step_ms:
            raise InvalidRequestError(
                "target bar must align to the base timeframe grid",
                target_bar_open_time_ms=target,
                base_timeframe=request.market.base_timeframe,
            )

        self._strategy_validator.execute(request.strategy)
        bounds = self._market_data.load_bounds(request.market)
        earliest = bounds.earliest_committed_open_time_ms
        latest = bounds.latest_committed_open_time_ms
        if bounds.state != "ready" or earliest is None or latest is None:
            raise MarketStreamNotReadyError(
                state=bounds.state,
                earliest_committed_open_time_ms=earliest,
                latest_committed_open_time_ms=latest,
            )
        if target < earliest or target > latest:
            raise TargetBarNotCommittedError(
                target_bar_open_time_ms=target,
                earliest_committed_open_time_ms=earliest,
                latest_committed_open_time_ms=latest,
            )

        requested_range = TimeRange(from_ms=earliest, to_ms=target + step_ms)
        requested_range.validate_alignment(request.market.base_timeframe)
        planned = self._feature_planner.execute(request.strategy)
        frame = self._indicator_evaluator.execute(
            IndicatorRangeRequest(
                market=request.market,
                time_range=requested_range,
                plan=planned.indicator_plan,
            )
        )
        if frame.market != request.market or frame.requested_range != requested_range:
            raise UpstreamContractError(
                "live FeatureFrame identity does not match the requested market range"
            )
        if not frame.time_ms or frame.time_ms[-1] != target:
            raise UpstreamContractError(
                "live FeatureFrame does not end on the requested target bar",
                target_bar_open_time_ms=target,
                actual_final_bar_open_time_ms=(frame.time_ms[-1] if frame.time_ms else None),
            )
        return LiveFeatureFrameBundle(
            strategy=request.strategy,
            market=request.market,
            target_bar_open_time_ms=target,
            target_index=len(frame.time_ms) - 1,
            bounds=bounds,
            requested_range=requested_range,
            planned_features=planned,
            frame=frame,
        )
