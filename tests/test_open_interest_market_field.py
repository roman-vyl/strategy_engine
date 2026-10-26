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


def test_all_none_open_interest_is_all_nan_and_ohlcv_views_are_unchanged() -> None:
    bars = tuple(_bar(index, None) for index in range(3))
    arrays = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars)

    assert np.isnan(arrays.array("open_interest")).all()
    assert OHLCV_FIELDS == ("open", "high", "low", "close", "volume")
    assert list(arrays.ohlcv_columns()) == list(OHLCV_FIELDS)
    assert list(arrays.dataframe().columns) == list(OHLCV_FIELDS)
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
