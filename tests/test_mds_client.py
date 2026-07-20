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


def test_mds_client_loads_strict_stream_bounds() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/streams/BTCUSDT.P/1m/bounds"
        return httpx.Response(
            200,
            json={
                "contract_version": "market_stream_bounds.v1",
                "ticker": "BTCUSDT.P",
                "timeframe": "1m",
                "state": "ready",
                "earliest_committed_open_time_ms": 0,
                "latest_committed_open_time_ms": 120_000,
            },
        )

    adapter = MarketDataServiceClient(
        "http://mds",
        client=httpx.Client(base_url="http://mds", transport=httpx.MockTransport(handler)),
    )
    bounds = adapter.load_bounds(MarketStream("BTCUSDT.P", "1m"))
    assert bounds.state == "ready"
    assert bounds.earliest_committed_open_time_ms == 0
    assert bounds.latest_committed_open_time_ms == 120_000


def test_mds_client_rejects_mismatched_bounds_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "contract_version": "market_stream_bounds.v1",
                "ticker": "ETHUSDT.P",
                "timeframe": "1m",
                "state": "ready",
                "earliest_committed_open_time_ms": 0,
                "latest_committed_open_time_ms": 120_000,
            },
        )

    adapter = MarketDataServiceClient(
        "http://mds",
        client=httpx.Client(base_url="http://mds", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamContractError):
        adapter.load_bounds(MarketStream("BTCUSDT.P", "1m"))


def test_mds_client_rejects_unsupported_or_malformed_bounds_contract() -> None:
    payloads = (
        {
            "contract_version": "market_stream_bounds.v2",
            "ticker": "BTCUSDT.P",
            "timeframe": "1m",
            "state": "ready",
            "earliest_committed_open_time_ms": 0,
            "latest_committed_open_time_ms": 120_000,
        },
        {
            "contract_version": "market_stream_bounds.v1",
            "ticker": "BTCUSDT.P",
            "timeframe": "1m",
            "state": "ready",
            "earliest_committed_open_time_ms": "zero",
            "latest_committed_open_time_ms": 120_000,
        },
    )
    for payload in payloads:

        def handler(request: httpx.Request, payload: dict[str, object] = payload) -> httpx.Response:
            return httpx.Response(200, json=payload)

        adapter = MarketDataServiceClient(
            "http://mds",
            client=httpx.Client(base_url="http://mds", transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(UpstreamContractError):
            adapter.load_bounds(MarketStream("BTCUSDT.P", "1m"))


def test_mds_client_maps_unknown_and_unavailable_bounds() -> None:
    from strategy_engine.domain.errors import MarketDataUnavailableError, MarketStreamNotFoundError

    for status_code, error_type in (
        (404, MarketStreamNotFoundError),
        (503, MarketDataUnavailableError),
    ):

        def handler(request: httpx.Request, status_code: int = status_code) -> httpx.Response:
            return httpx.Response(status_code, json={"error": "fixture"})

        adapter = MarketDataServiceClient(
            "http://mds",
            client=httpx.Client(base_url="http://mds", transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(error_type):
            adapter.load_bounds(MarketStream("BTCUSDT.P", "1m"))


def test_mds_client_rejects_inverted_bounds_as_upstream_contract_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "contract_version": "market_stream_bounds.v1",
                "ticker": "BTCUSDT.P",
                "timeframe": "1m",
                "state": "ready",
                "earliest_committed_open_time_ms": 120_000,
                "latest_committed_open_time_ms": 60_000,
            },
        )

    adapter = MarketDataServiceClient(
        "http://mds",
        client=httpx.Client(base_url="http://mds", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamContractError, match="inverted stream bounds"):
        adapter.load_bounds(MarketStream("BTCUSDT.P", "1m"))
