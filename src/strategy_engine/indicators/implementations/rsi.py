"""BBB-compatible rolling-mean Relative Strength Index implementation."""

from __future__ import annotations

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature


def validate_rsi_feature(feature: PlannedFeature) -> None:
    if feature.source != "close":
        raise InvalidRequestError(
            "RSI source must be close",
            output_id=feature.output_id,
            source=feature.source,
        )
    period = feature.parameters.get("period")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise InvalidRequestError(
            "RSI period must be a positive integer",
            output_id=feature.output_id,
            period=period,
        )
    if set(feature.parameters) != {"period"}:
        raise InvalidRequestError(
            "RSI parameters must contain only period",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            "RSI does not accept feature dependencies",
            output_id=feature.output_id,
        )


def rsi_rolling_mean(close: pd.Series, *, period: int) -> pd.Series:
    """Match BBB simple rolling-gain/loss RSI semantics exactly."""

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
