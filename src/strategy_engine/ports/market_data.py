"""Market Data Service abstraction."""

from __future__ import annotations

from typing import Protocol

from strategy_engine.domain.market import MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange


class MarketDataPort(Protocol):
    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame: ...
