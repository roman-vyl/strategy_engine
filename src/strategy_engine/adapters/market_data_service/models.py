"""MDS HTTP response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr


class CandlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_time_ms: StrictInt
    open: StrictStr
    high: StrictStr
    low: StrictStr
    close: StrictStr
    volume: StrictStr


class CandleRangePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: StrictStr
    timeframe: StrictStr
    from_ms: StrictInt
    to_ms: StrictInt
    market_data_hash: StrictStr
    candles: list[CandlePayload]


class StreamBoundsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: StrictStr
    ticker: StrictStr
    timeframe: StrictStr
    state: StrictStr
    earliest_committed_open_time_ms: StrictInt | None
    latest_committed_open_time_ms: StrictInt | None
