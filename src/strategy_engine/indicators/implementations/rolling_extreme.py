"""Maximum or minimum of a source over the last `period` candles of the
feature timeframe, the current one included (OpenSpec
`w8-rolling-extreme-v1`); missing until `period` finite values fill the
window. As any higher-timeframe feature, the base bars see the value of the
last completed candle."""

from __future__ import annotations

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.market_arrays import OPEN_INTEREST_FIELD

ROLLING_EXTREME_KINDS = ("rolling_max", "rolling_min")
ROLLING_EXTREME_SOURCES = ("open", "high", "low", "close", OPEN_INTEREST_FIELD)


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
