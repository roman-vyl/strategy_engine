"""Canonical market identity and OHLCV frame contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.ranges import TimeRange, timeframe_duration_ms

_TICKER_RE = re.compile(r"^[A-Z0-9]+\.P$")
_TIMEFRAME_RE = re.compile(r"^[1-9][0-9]*[mhdw]$")


@dataclass(frozen=True, slots=True)
class MarketStream:
    ticker: str
    base_timeframe: str

    def __post_init__(self) -> None:
        if not _TICKER_RE.fullmatch(self.ticker):
            raise InvalidRequestError("ticker must be canonical .P identity", ticker=self.ticker)
        if not _TIMEFRAME_RE.fullmatch(self.base_timeframe):
            raise InvalidRequestError(
                "base_timeframe must be canonical textual timeframe",
                base_timeframe=self.base_timeframe,
            )
        timeframe_duration_ms(self.base_timeframe)


@dataclass(frozen=True, slots=True)
class MarketBar:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class MarketFrame:
    market: MarketStream
    requested_range: TimeRange
    bars: tuple[MarketBar, ...]
    market_data_hash: str

    def __post_init__(self) -> None:
        step_ms = timeframe_duration_ms(self.market.base_timeframe)
        expected = self.requested_range.from_ms
        for bar in self.bars:
            if bar.open_time_ms != expected:
                raise InvalidRequestError(
                    "market frame must contain a complete ordered grid",
                    expected_open_time_ms=expected,
                    actual_open_time_ms=bar.open_time_ms,
                )
            expected += step_ms
        if expected != self.requested_range.to_ms:
            raise InvalidRequestError(
                "market frame does not cover the complete requested range",
                expected_to_ms=self.requested_range.to_ms,
                actual_to_ms=expected,
            )
