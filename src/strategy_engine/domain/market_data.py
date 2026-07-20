"""Market-data coverage contracts owned by Strategy Engine adapters."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_engine.domain.errors import UpstreamContractError
from strategy_engine.domain.market import MarketStream


@dataclass(frozen=True, slots=True)
class StreamBounds:
    """Strict projection of the MDS ``market_stream_bounds.v1`` contract."""

    market: MarketStream
    state: str
    earliest_committed_open_time_ms: int | None
    latest_committed_open_time_ms: int | None

    def __post_init__(self) -> None:
        earliest = self.earliest_committed_open_time_ms
        latest = self.latest_committed_open_time_ms
        if earliest is not None and earliest < 0:
            raise UpstreamContractError(
                "Market Data Service returned a negative earliest committed bar",
                earliest_committed_open_time_ms=earliest,
            )
        if latest is not None and latest < 0:
            raise UpstreamContractError(
                "Market Data Service returned a negative latest committed bar",
                latest_committed_open_time_ms=latest,
            )
        if earliest is not None and latest is not None and earliest > latest:
            raise UpstreamContractError(
                "Market Data Service returned inverted stream bounds",
                earliest_committed_open_time_ms=earliest,
                latest_committed_open_time_ms=latest,
            )
