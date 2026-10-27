"""Shape of each candle of the feature timeframe (OpenSpec `htf-candle-shape-v1`):
its body over the Wilder ATR of the candle before it, and the position of its
close in its range. As any higher-timeframe feature, the base bars see the
value of the last completed candle."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.implementations.atr import atr_wilder, validate_atr_feature


def validate_candle_body_atr_feature(feature: PlannedFeature) -> None:
    # The same parameters as the Wilder ATR it is normalised by.
    validate_atr_feature(feature)


def validate_candle_close_position_feature(feature: PlannedFeature) -> None:
    if feature.source != "close":
        raise InvalidRequestError(
            "candle close position source must be close",
            output_id=feature.output_id,
            source=feature.source,
        )
    if feature.parameters:
        raise InvalidRequestError(
            "candle close position has no parameters",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            "candle close position does not accept feature dependencies",
            output_id=feature.output_id,
        )


def candle_body_atr(frame: pd.DataFrame, *, period: int) -> pd.Series:
    """`(close - open) / atr_wilder(period)` of the previous candle; missing
    while that ATR is missing or not above 0."""

    atr = atr_wilder(
        frame["high"].astype(float),
        frame["low"].astype(float),
        frame["close"].astype(float),
        period=period,
    ).shift(1)
    body = frame["close"].astype(float) - frame["open"].astype(float)
    return (body / atr.where(atr > 0)).astype(float)


def candle_close_position(frame: pd.DataFrame) -> pd.Series:
    """`(close - low) / (high - low)`; missing on a candle without range."""

    low = frame["low"].astype(float)
    span = frame["high"].astype(float) - low
    value = (frame["close"].astype(float) - low) / span.where(span > 0)
    return value.astype(np.float64)
