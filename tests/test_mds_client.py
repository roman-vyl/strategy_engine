from __future__ import annotations

import httpx
import pytest

from strategy_engine.adapters.market_data_service.client import MarketDataServiceClient
from strategy_engine.domain.errors import UpstreamContractError
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange


def client_for(payload: dict[str, object], status_code: int = 200) -> MarketDataServiceClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/candles"
        return httpx.Response(status_code, json=payload)

    client = httpx.Client(
        base_url="http://mds",
        transport=httpx.MockTransport(handler),
    )
    return MarketDataServiceClient("http://mds", client=client)


def test_mds_client_parses_complete_decimal_text_grid() -> None:
    adapter = client_for(
        {
            "ticker": "BTCUSDT.P",
            "timeframe": "1m",
            "from_ms": 0,
            "to_ms": 120_000,
            "market_data_hash": "mds-hash",
            "candles": [
                {
                    "open_time_ms": 0,
                    "open": "1.2300",
                    "high": "2",
                    "low": "1",
                    "close": "1.5",
                    "volume": "10.500",
                },
                {
                    "open_time_ms": 60_000,
                    "open": "1.5",
                    "high": "2.1",
                    "low": "1.4",
                    "close": "2",
                    "volume": "12",
                },
            ],
        }
    )
    frame = adapter.load_range(MarketStream("BTCUSDT.P", "1m"), TimeRange(0, 120_000))
    assert [bar.open_time_ms for bar in frame.bars] == [0, 60_000]
    assert str(frame.bars[0].open) == "1.2300"
    assert frame.market_data_hash == "mds-hash"


def test_mds_client_rejects_incomplete_or_mismatched_response() -> None:
    adapter = client_for(
        {
            "ticker": "BTCUSDT.P",
            "timeframe": "1m",
            "from_ms": 0,
            "to_ms": 120_000,
            "market_data_hash": "mds-hash",
            "candles": [
                {
                    "open_time_ms": 0,
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "1.5",
                    "volume": "10",
                }
            ],
        }
    )
    with pytest.raises(UpstreamContractError):
        adapter.load_range(MarketStream("BTCUSDT.P", "1m"), TimeRange(0, 120_000))
