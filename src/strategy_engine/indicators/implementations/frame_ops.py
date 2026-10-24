"""Shared pandas frame operations for BBB-compatible range indicators."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.market_arrays import MarketArrays


def pandas_frequency(timeframe: str) -> str:
    if timeframe.endswith("m"):
        return f"{int(timeframe[:-1])}min"
    if timeframe.endswith("h"):
        return f"{int(timeframe[:-1])}h"
    if timeframe.endswith("d"):
        return f"{int(timeframe[:-1])}D"
    if timeframe.endswith("w"):
        # Weeks start on Monday 00:00 UTC, as exchange weekly candles
        # (OpenSpec `htf-candle-shape-v1`); a plain "W" bins from Sunday.
        return f"{int(timeframe[:-1])}W-MON"
    raise InvalidRequestError("unsupported indicator timeframe", timeframe=timeframe)


def feature_timeframe(feature_timeframe: str, base_timeframe: str) -> str:
    return base_timeframe if feature_timeframe == "base" else feature_timeframe


def market_frame_to_dataframe(market_frame: MarketFrame) -> pd.DataFrame:
    """Standalone float64 OHLCV frame for one `MarketFrame`, through the
    shared `MarketArrays` conversion. Evaluation paths build `MarketArrays`
    once and call `.dataframe()` on it instead of converting per call."""

    return MarketArrays.from_market_frame(market_frame).dataframe()


def resample_ohlcv(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    return (
        frame.resample(pandas_frequency(timeframe), label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def align_completed_to_base(
    feature: pd.Series,
    *,
    timeframe: str,
    base_index: pd.Index,
) -> pd.Series:
    completed = feature.copy()
    # A fixed duration: an anchored weekly offset would roll to its anchor day.
    completed.index = completed.index + pd.Timedelta(timeframe_duration_ms(timeframe), unit="ms")
    return completed.reindex(base_index, method="ffill")


def serialize_value(value: float) -> str | None:
    if pd.isna(value):
        return None
    return normalized_decimal_text(Decimal(str(float(value))))
