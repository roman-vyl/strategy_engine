"""Coarse-grained managed policy replay application service."""

from __future__ import annotations

from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.contracts import IndicatorRangeRequest
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import ManagedReplayRequest
from strategy_engine.strategies.ema_pullback.contexts import build_context_bundle
from strategy_engine.strategies.ema_pullback.managed import (
    ManagedReplayResult,
    evaluate_managed_replay,
)
from strategy_engine.strategies.ema_pullback.managed_composite import (
    composites_need_context_bundle,
)


class EvaluateManagedReplay:
    def __init__(
        self,
        planner: BuildStrategyFeaturePlan,
        indicators: EvaluateIndicatorRange,
        validator: ValidateStrategySpec,
    ) -> None:
        self._planner = planner
        self._indicators = indicators
        self._validator = validator

    def execute(self, request: ManagedReplayRequest) -> ManagedReplayResult:
        request.time_range.validate_alignment(request.market.base_timeframe)
        self._validator.execute(request.strategy)
        planned = self._planner.execute(request.strategy)
        frame = self._indicators.execute(
            IndicatorRangeRequest(request.market, request.time_range, planned.indicator_plan)
        )
        raw_spec = request.strategy.raw_spec
        # Only a composite phase condition with a `state` predicate needs HTF
        # state (composite-managed-phase-condition-v1 design D7); every other
        # spec builds no bundle, exactly as before.
        bundle = (
            build_context_bundle(raw_spec, frame, planned)
            if composites_need_context_bundle(raw_spec)
            else None
        )
        return evaluate_managed_replay(
            raw_spec,
            frame,
            planned,
            trade_id=request.trade_id,
            side=request.side,
            entry_time_ms=request.entry_time_ms,
            entry_price=request.entry_price,
            bundle=bundle,
        )
