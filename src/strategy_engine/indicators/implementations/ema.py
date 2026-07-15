"""BBB-compatible exponential moving-average implementation."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.indicators.contracts import FeatureFrame, IndicatorPlan, PlannedFeature

_ALLOWED_SOURCES = ("open", "high", "low", "close")


def validate_ema_feature(feature: PlannedFeature) -> None:
    if feature.source not in _ALLOWED_SOURCES:
        raise InvalidRequestError(
            "EMA source must be open, high, low, or close",
            output_id=feature.output_id,
            source=feature.source,
        )
    period = feature.parameters.get("period")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise InvalidRequestError(
            "EMA period must be a positive integer",
            output_id=feature.output_id,
            period=period,
        )
    if set(feature.parameters) != {"period"}:
        raise InvalidRequestError(
            "EMA parameters must contain only period",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            "EMA does not accept feature dependencies",
            output_id=feature.output_id,
        )


class EmaIndicatorEvaluator:
    """Compatibility wrapper around the registered range evaluator."""

    def evaluate(self, market_frame: MarketFrame, plan: IndicatorPlan) -> FeatureFrame:
        from strategy_engine.indicators.implementations.range_evaluator import (
            RangeIndicatorEvaluator,
        )

        for feature in plan.features:
            if feature.kind != "ema":
                raise InvalidRequestError(
                    "EMA evaluator received unsupported indicator kind",
                    kind=feature.kind,
                )
        return RangeIndicatorEvaluator().evaluate(market_frame, plan)
