"""Shared pandas frame operations for BBB-compatible range indicators."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.domain.values import normalized_decimal_text


def pandas_frequency(timeframe: str) -> str:
    if timeframe.endswith("m"):
        return f"{int(timeframe[:-1])}min"
    if timeframe.endswith("h"):
        return f"{int(timeframe[:-1])}h"
    if timeframe.endswith("d"):
        return f"{int(timeframe[:-1])}D"
    if timeframe.endswith("w"):
        return f"{int(timeframe[:-1])}W"
    raise InvalidRequestError("unsupported indicator timeframe", timeframe=timeframe)


def feature_timeframe(feature_timeframe: str, base_timeframe: str) -> str:
    return base_timeframe if feature_timeframe == "base" else feature_timeframe


def market_frame_to_dataframe(market_frame: MarketFrame) -> pd.DataFrame:
    index = pd.to_datetime(
        [bar.open_time_ms for bar in market_frame.bars],
        unit="ms",
        utc=True,
    )
    return pd.DataFrame(
        {
            "open": [float(bar.open) for bar in market_frame.bars],
            "high": [float(bar.high) for bar in market_frame.bars],
            "low": [float(bar.low) for bar in market_frame.bars],
            "close": [float(bar.close) for bar in market_frame.bars],
            "volume": [float(bar.volume) for bar in market_frame.bars],
        },
        index=index,
    )


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
    completed.index = completed.index + pd.tseries.frequencies.to_offset(
        pandas_frequency(timeframe)
    )
    return completed.reindex(base_index, method="ffill")


def serialize_value(value: float) -> str | None:
    if pd.isna(value):
        return None
    return normalized_decimal_text(Decimal(str(float(value))))
