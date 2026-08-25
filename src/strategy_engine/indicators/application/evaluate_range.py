"""Indicator range evaluation orchestration."""

from __future__ import annotations

from strategy_engine.domain.errors import EvaluationInvariantError, UnsupportedCapabilityError
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
        if request.market_frame is not None:
            # batch-market-dataset-reuse: fail closed if an internal caller
            # ever threads a preloaded MarketFrame that does not actually
            # match this request's identity -- silently accepting a
            # mismatched frame would let a result be computed against the
            # wrong market/range/dataset without any observable signal.
            if request.market_frame.market != request.market:
                raise EvaluationInvariantError(
                    "preloaded market frame does not match requested market",
                    expected_ticker=request.market.ticker,
                    expected_timeframe=request.market.base_timeframe,
                    actual_ticker=request.market_frame.market.ticker,
                    actual_timeframe=request.market_frame.market.base_timeframe,
                )
            if request.market_frame.requested_range != request.time_range:
                raise EvaluationInvariantError(
                    "preloaded market frame does not match requested time range",
                    expected_from_ms=request.time_range.from_ms,
                    expected_to_ms=request.time_range.to_ms,
                    actual_from_ms=request.market_frame.requested_range.from_ms,
                    actual_to_ms=request.market_frame.requested_range.to_ms,
                )
            if (
                request.expected_market_data_hash is not None
                and request.market_frame.market_data_hash != request.expected_market_data_hash
            ):
                raise EvaluationInvariantError(
                    "preloaded market frame does not match expected market data hash",
                    expected_market_data_hash=request.expected_market_data_hash,
                    actual_market_data_hash=request.market_frame.market_data_hash,
                )
            market_frame = request.market_frame
        elif request.expected_market_data_hash is None:
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
