"""Maximum or minimum of a source over the last `period` candles of the
feature timeframe, the current one included (OpenSpec
`w8-rolling-extreme-v1`), and the sum of a source over `period` candles
ending `lag` candles back (`vol1h-rolling-sum-v1`); missing until `period`
finite values fill the window. As any higher-timeframe feature, the base
bars see the value of the last completed candle."""

from __future__ import annotations

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.market_arrays import OHLCV_FIELDS, OPEN_INTEREST_FIELD

ROLLING_EXTREME_KINDS = ("rolling_max", "rolling_min")
ROLLING_EXTREME_SOURCES = ("open", "high", "low", "close", OPEN_INTEREST_FIELD)
ROLLING_SUM_KIND = "rolling_sum"
# Every field the Engine carries on a bar; a field added later is a source here.
ROLLING_SUM_SOURCES = (*OHLCV_FIELDS, OPEN_INTEREST_FIELD)


def validate_rolling_extreme_feature(feature: PlannedFeature) -> None:
    if feature.source not in ROLLING_EXTREME_SOURCES:
        raise InvalidRequestError(
            f"{feature.kind} source must be one of {', '.join(ROLLING_EXTREME_SOURCES)}",
            output_id=feature.output_id,
            source=feature.source,
        )
    period = feature.parameters.get("period")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise InvalidRequestError(
            f"{feature.kind} period must be a positive integer",
            output_id=feature.output_id,
            period=period,
        )
    if set(feature.parameters) != {"period"}:
        raise InvalidRequestError(
            f"{feature.kind} parameters must contain only period",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            f"{feature.kind} does not accept feature dependencies",
            output_id=feature.output_id,
        )


def rolling_extreme(frame: pd.DataFrame, *, kind: str, source: str, period: int) -> pd.Series:
    window = frame[source].astype(float).rolling(period, min_periods=period)
    return (window.max() if kind == "rolling_max" else window.min()).astype(float)


def rolling_sum_lag(feature: PlannedFeature) -> int:
    return int(feature.parameters.get("lag", 0))


def validate_rolling_sum_feature(feature: PlannedFeature) -> None:
    if feature.source not in ROLLING_SUM_SOURCES:
        raise InvalidRequestError(
            f"rolling_sum source must be one of {', '.join(ROLLING_SUM_SOURCES)}",
            output_id=feature.output_id,
            source=feature.source,
        )
    period = feature.parameters.get("period")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise InvalidRequestError(
            "rolling_sum period must be a positive integer",
            output_id=feature.output_id,
            period=period,
        )
    lag = feature.parameters.get("lag", 0)
    if isinstance(lag, bool) or not isinstance(lag, int) or lag < 0:
        raise InvalidRequestError(
            "rolling_sum lag must be a non-negative integer",
            output_id=feature.output_id,
            lag=lag,
        )
    if not set(feature.parameters) <= {"period", "lag"}:
        raise InvalidRequestError(
            "rolling_sum parameters must contain only period and lag",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            "rolling_sum does not accept feature dependencies",
            output_id=feature.output_id,
        )


def rolling_sum(frame: pd.DataFrame, *, source: str, period: int, lag: int) -> pd.Series:
    total = frame[source].astype(float).rolling(period, min_periods=period).sum()
    return total.shift(lag).astype(float)
