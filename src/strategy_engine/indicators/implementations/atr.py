"""BBB-compatible Average True Range implementation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature


def validate_atr_feature(feature: PlannedFeature) -> None:
    if feature.source != "close":
        raise InvalidRequestError(
            "ATR source must be close for BBB compatibility",
            output_id=feature.output_id,
            source=feature.source,
        )
    period = feature.parameters.get("period")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise InvalidRequestError(
            "ATR period must be a positive integer",
            output_id=feature.output_id,
            period=period,
        )
    if set(feature.parameters) != {"period"}:
        raise InvalidRequestError(
            "ATR parameters must contain only period",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            "ATR does not accept feature dependencies",
            output_id=feature.output_id,
        )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    high_low = high - low
    high_prev_close = (high - prev_close).abs()
    low_prev_close = (low - prev_close).abs()
    return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)


def atr_wilder(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    period: int,
) -> pd.Series:
    """Wilder ATR as the research reference computes it: the first true range
    is `high - low`, the seed (at position `period - 1`) is the mean of the
    first `period` true ranges, then `(atr * (period - 1) + tr) / period`;
    values before the seed are missing (OpenSpec `b1-candle-ratio-v1`, D5)."""

    tr = true_range(high, low, close).to_numpy(dtype=float).copy()
    if len(tr):
        tr[0] = float(high.iloc[0]) - float(low.iloc[0])
    out = np.full(len(tr), np.nan)
    if len(tr) >= period:
        value = float(tr[:period].mean())
        out[period - 1] = value
        for index in range(period, len(tr)):
            value = (value * (period - 1) + tr[index]) / period
            out[index] = value
    return pd.Series(out, index=high.index)


def atr_rolling_mean(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    period: int,
) -> pd.Series:
    return (
        true_range(high, low, close)
        .rolling(
            window=period,
            min_periods=period,
        )
        .mean()
    )
