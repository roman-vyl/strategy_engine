"""engine-open-interest-market-field-v1: open interest as an optional market field."""

from __future__ import annotations

import gzip
import json
import math
from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from parity import harness
from parity.corpus import all_cases

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.implementations.frame_ops import resample_ohlcv
from strategy_engine.indicators.market_arrays import OHLCV_FIELDS, MarketArrays


def _bar(index: int, open_interest: Decimal | None) -> MarketBar:
    return MarketBar(
        index * 300_000,
        Decimal("1"),
        Decimal("2"),
        Decimal("0.5"),
        Decimal("1.5"),
        Decimal("10"),
        open_interest,
    )


def test_open_interest_array_has_own_values_and_nan_without_fill() -> None:
    bars = (
        _bar(0, None),
        _bar(1, Decimal("82345.67")),
        _bar(2, None),
        _bar(3, Decimal("82400.1")),
    )
    arrays = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars)

    values = arrays.values("open_interest")
    assert math.isnan(values[0]) and math.isnan(values[2])
    assert values[1] == float(Decimal("82345.67")) and values[3] == float(Decimal("82400.1"))
    array = arrays.array("open_interest")
    assert array.dtype == np.float64 and not array.flags.writeable
    assert arrays.array("open_interest") is array
    assert arrays.values("open_interest") is values


def test_all_none_open_interest_is_all_nan_and_ohlcv_columns_are_unchanged() -> None:
    bars = tuple(_bar(index, None) for index in range(3))
    arrays = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars)

    assert np.isnan(arrays.array("open_interest")).all()
    assert OHLCV_FIELDS == ("open", "high", "low", "close", "volume")
    assert list(arrays.ohlcv_columns()) == list(OHLCV_FIELDS)
    frame = arrays.dataframe()
    assert list(frame.columns) == [*OHLCV_FIELDS, "open_interest"]
    assert frame["open_interest"].isna().all()
    with pytest.raises(KeyError):
        arrays.values("turnover")


def _fixture_with_open_interest() -> bytes:
    payload = json.loads(harness.market_fixture_bytes())
    for index, candle in enumerate(payload["candles"]):
        # Values on most bars, null runs and absent fields in between.
        if index % 7 == 3:
            candle["open_interest"] = None
        elif index % 11 != 5:
            candle["open_interest"] = f"{50000 + index}.{index % 10}"
    return gzip.compress(json.dumps(payload).encode())


def _record(case: Any) -> dict[str, Any]:
    record, _store = harness.record_payload(case.name, case.payload())
    return record


def test_strategies_give_identical_results_with_and_without_open_interest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = all_cases()
    without = [_record(case) for case in cases]

    body = gzip.decompress(_fixture_with_open_interest())
    monkeypatch.setattr(harness, "market_fixture_bytes", lambda: body)
    client = harness._fixture_mds_client("http://fixture")
    meta = harness.market_fixture_meta()
    frame = client.load_range(
        MarketStream(meta["ticker"], meta["timeframe"]),
        TimeRange(meta["from_ms"], meta["to_ms"]),
    )
    carried = [bar.open_interest for bar in frame.bars]
    assert sum(value is not None for value in carried) > len(carried) // 2
    assert any(value is None for value in carried)
    with_oi = [_record(case) for case in cases]

    assert len(without) == len(cases)
    for case, before, after in zip(cases, without, with_oi, strict=True):
        assert after == before, case.name


def test_indicator_frame_carries_open_interest_like_volume() -> None:
    bars = (_bar(0, Decimal("100.5")), _bar(1, None), _bar(2, Decimal("101.25")))
    arrays = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars)
    frame = arrays.dataframe()

    assert frame["open_interest"].dtype == np.float64
    assert frame["open_interest"].to_numpy().tobytes() == arrays.array("open_interest").tobytes()
    assert not np.shares_memory(frame["open_interest"].to_numpy(), arrays.array("open_interest"))


def test_higher_timeframe_open_interest_is_the_last_bar_value_never_a_sum() -> None:
    # 1h candles of twelve 5m bars: the first has every value, the second
    # lacks open interest on its last bar only, the third on an inner bar.
    values: list[Decimal | None] = [Decimal(1000 + index) for index in range(36)]
    values[23] = None
    values[30] = None
    bars = tuple(_bar(index, value) for index, value in enumerate(values))
    frame = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars).dataframe()

    hourly = resample_ohlcv(frame, "1h")
    assert list(hourly.columns) == [*OHLCV_FIELDS, "open_interest"]
    oi = hourly["open_interest"].tolist()
    assert oi[0] == 1011.0
    assert math.isnan(oi[1])
    assert oi[2] == 1035.0
    assert hourly["volume"].tolist() == [120.0, 120.0, 120.0]


def test_higher_timeframe_ohlcv_is_unchanged_by_the_open_interest_column() -> None:
    bars = tuple(_bar(index, Decimal(index)) for index in range(30))
    frame = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars).dataframe()

    with_oi = resample_ohlcv(frame, "1h")
    without_oi = resample_ohlcv(frame.drop(columns="open_interest"), "1h")
    assert list(without_oi.columns) == list(OHLCV_FIELDS)
    for field in OHLCV_FIELDS:
        assert with_oi[field].to_numpy().tobytes() == without_oi[field].to_numpy().tobytes()
    assert with_oi.index.equals(without_oi.index)
