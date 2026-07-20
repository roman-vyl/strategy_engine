"""HTTP adapter for Market Data Service canonical candle range API."""

from __future__ import annotations

from typing import Any

import httpx

from strategy_engine.adapters.market_data_service.models import (
    CandleRangePayload,
    StreamBoundsPayload,
)
from strategy_engine.domain.errors import (
    MarketDataUnavailableError,
    UnknownResourceError,
    UpstreamContractError,
)
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange, timeframe_duration_ms
from strategy_engine.domain.values import parse_decimal_text


class MarketDataServiceClient:
    def __init__(
        self,
        base_url: str,
        *,
        connect_timeout_seconds: float = 2.0,
        read_timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owned_client = client is None
        timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=read_timeout_seconds,
            pool=connect_timeout_seconds,
        )
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def load_bounds(self, market: MarketStream) -> StreamBounds:
        try:
            response = self._client.get(
                f"/v1/streams/{market.ticker}/{market.base_timeframe}/bounds"
            )
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError("Market Data Service request failed") from exc
        if response.status_code != 200:
            if response.status_code == 404:
                raise UnknownResourceError(
                    "Market Data Service stream is unknown",
                    ticker=market.ticker,
                    timeframe=market.base_timeframe,
                )
            self._raise_upstream_error(response)
        try:
            payload = StreamBoundsPayload.model_validate(response.json())
        except Exception as exc:
            raise UpstreamContractError("invalid Market Data Service bounds response") from exc
        if payload.contract_version != "market_stream_bounds.v1":
            raise UpstreamContractError(
                "unsupported Market Data Service bounds contract",
                contract_version=payload.contract_version,
            )
        if payload.ticker != market.ticker or payload.timeframe != market.base_timeframe:
            raise UpstreamContractError(
                "Market Data Service bounds identity does not match request",
                expected_ticker=market.ticker,
                actual_ticker=payload.ticker,
                expected_timeframe=market.base_timeframe,
                actual_timeframe=payload.timeframe,
            )
        return StreamBounds(
            market=market,
            state=payload.state,
            earliest_committed_open_time_ms=payload.earliest_committed_open_time_ms,
            latest_committed_open_time_ms=payload.latest_committed_open_time_ms,
        )

    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame:
        time_range.validate_alignment(market.base_timeframe)
        try:
            if expected_market_data_hash is None:
                response = self._client.get(
                    "/v1/candles",
                    params={
                        "ticker": market.ticker,
                        "timeframe": market.base_timeframe,
                        "from_ms": time_range.from_ms,
                        "to_ms": time_range.to_ms,
                    },
                )
            else:
                response = self._client.post(
                    "/v1/historical-candles",
                    json={
                        "ticker": market.ticker,
                        "timeframe": market.base_timeframe,
                        "from_ms": time_range.from_ms,
                        "to_ms": time_range.to_ms,
                        "expected_market_data_hash": expected_market_data_hash,
                    },
                )
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError("Market Data Service request failed") from exc
        if response.status_code != 200:
            self._raise_upstream_error(response)
        try:
            payload = CandleRangePayload.model_validate(response.json())
        except Exception as exc:
            raise UpstreamContractError("invalid Market Data Service response") from exc
        if (
            payload.ticker != market.ticker
            or payload.timeframe != market.base_timeframe
            or payload.from_ms != time_range.from_ms
            or payload.to_ms != time_range.to_ms
        ):
            raise UpstreamContractError(
                "Market Data Service response identity does not match request"
            )
        step_ms = timeframe_duration_ms(market.base_timeframe)
        expected = time_range.from_ms
        bars: list[MarketBar] = []
        for candle in payload.candles:
            if candle.open_time_ms != expected:
                raise UpstreamContractError(
                    "Market Data Service returned a gapped or unordered range",
                    expected_open_time_ms=expected,
                    actual_open_time_ms=candle.open_time_ms,
                )
            bars.append(
                MarketBar(
                    open_time_ms=candle.open_time_ms,
                    open=parse_decimal_text(candle.open),
                    high=parse_decimal_text(candle.high),
                    low=parse_decimal_text(candle.low),
                    close=parse_decimal_text(candle.close),
                    volume=parse_decimal_text(candle.volume),
                )
            )
            expected += step_ms
        if expected != time_range.to_ms:
            raise UpstreamContractError(
                "Market Data Service returned an incomplete range",
                expected_to_ms=time_range.to_ms,
                actual_to_ms=expected,
            )
        return MarketFrame(
            market=market,
            requested_range=time_range,
            bars=tuple(bars),
            market_data_hash=payload.market_data_hash,
        )

    @staticmethod
    def _raise_upstream_error(response: httpx.Response) -> None:
        details: dict[str, Any] = {"status_code": response.status_code}
        try:
            body = response.json()
            if isinstance(body, dict):
                details["upstream_error"] = body.get("error")
                details["upstream_message"] = body.get("message") or body.get("detail")
        except ValueError:
            details["body"] = response.text[:500]
        if response.status_code >= 500:
            raise MarketDataUnavailableError("Market Data Service is unavailable", **details)
        raise UpstreamContractError("Market Data Service rejected the request", **details)
