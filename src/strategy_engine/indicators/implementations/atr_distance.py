"""BBB-compatible ATR-distance derived feature."""

from __future__ import annotations

from numbers import Real

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature


def validate_atr_distance_feature(feature: PlannedFeature) -> None:
    if feature.source is not None:
        raise InvalidRequestError(
            "atr_distance source must be null",
            output_id=feature.output_id,
        )
    if set(feature.parameters) != {"multiplier"}:
        raise InvalidRequestError(
            "atr_distance parameters must contain only multiplier",
            output_id=feature.output_id,
        )
    multiplier = feature.parameters["multiplier"]
    if isinstance(multiplier, bool) or not isinstance(multiplier, Real):
        raise InvalidRequestError(
            "atr_distance multiplier must be a positive number",
            output_id=feature.output_id,
        )
    if float(multiplier) <= 0:
        raise InvalidRequestError(
            "atr_distance multiplier must be greater than zero",
            output_id=feature.output_id,
        )
    if len(feature.dependencies) != 1:
        raise InvalidRequestError(
            "atr_distance requires exactly one ATR dependency",
            output_id=feature.output_id,
        )
