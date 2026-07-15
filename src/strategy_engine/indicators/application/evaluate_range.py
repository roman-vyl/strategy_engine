"""Indicator range evaluation orchestration."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.indicators.contracts import FeatureFrame, IndicatorRangeRequest
from strategy_engine.indicators.ports import IndicatorRegistryPort
from strategy_engine.ports.market_data import MarketDataPort


class EvaluateIndicatorRange:
    def __init__(
        self,
        registry: IndicatorRegistryPort,
        market_data: MarketDataPort,
        validator: ValidateIndicatorPlan,
    ) -> None:
        self._registry = registry
        self._market_data = market_data
        self._validator = validator

    def execute(self, request: IndicatorRangeRequest) -> FeatureFrame:
        request.time_range.validate_alignment(request.market.base_timeframe)
        self._validator.execute(request.plan)
        evaluator = self._registry.evaluator()
        if evaluator is None:
            raise UnsupportedCapabilityError("indicator_range_evaluation")
        if request.expected_market_data_hash is None:
            market_frame = self._market_data.load_range(
                request.market,
                request.time_range,
            )
        else:
            market_frame = self._market_data.load_range(
                request.market,
                request.time_range,
                expected_market_data_hash=request.expected_market_data_hash,
            )
        return evaluator.evaluate(market_frame, request.plan)
