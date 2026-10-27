"""Rolling extreme features (OpenSpec `w8-rolling-extreme-v1`): `rolling_max` and
`rolling_min` over OHLC and open interest against a loop, missing until the window is
full or while it holds a missing value, on a higher timeframe as the last completed
candle; request validation, labels, identity and live warm-up; open interest as a
base-bar field operand."""

from __future__ import annotations

import math
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from test_ema_pullback_predicates_a2 import _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar
from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.indicators.implementations.frame_ops import (
    align_completed_to_base,
    resample_ohlcv,
)
from strategy_engine.indicators.implementations.range_evaluator import resolve_feature
from strategy_engine.indicators.implementations.rolling_extreme import rolling_extreme
from strategy_engine.indicators.market_arrays import MarketArrays
from strategy_engine.strategies.ema_pullback.predicates import _values


def _frame(bars: int, seed: int, gap: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-03", periods=bars, freq="5min", tz="UTC")
    c = 100 + np.cumsum(rng.normal(0, 1, bars))
    oi = 70_000 * np.exp(np.cumsum(rng.normal(0, 0.01, bars)))
    oi[: bars // 10] = math.nan  # open interest starts later than the candles
    if gap is not None:
        oi[gap] = math.nan
    return pd.DataFrame(
        {"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0, "open_interest": oi},
        index=index,
    )


def _loop(x: np.ndarray, period: int, kind: str) -> np.ndarray:
    out = np.full(len(x), math.nan)
    for t in range(period - 1, len(x)):
        window = x[t - period + 1 : t + 1]
        if np.isfinite(window).all():
            out[t] = window.max() if kind == "rolling_max" else window.min()
    return out


@pytest.mark.parametrize("kind", ["rolling_max", "rolling_min"])
@pytest.mark.parametrize("source", ["high", "open_interest"])
@pytest.mark.parametrize("gap", [None, 700])
def test_base_values_match_the_loop(kind: str, source: str, gap: int | None) -> None:
    frame = _frame(1500, 3, gap)
    got = rolling_extreme(frame, kind=kind, source=source, period=96).to_numpy()
    expected = _loop(frame[source].to_numpy(), 96, kind)
    np.testing.assert_array_equal(got, expected)
    assert np.isfinite(got).sum() > 500 and np.isnan(got).any()


def test_higher_timeframe_is_the_last_completed_candle() -> None:
    frame = _frame(2000, 4)
    htf = resample_ohlcv(frame, "1h")
    values = rolling_extreme(htf, kind="rolling_max", source="open_interest", period=5)
    got = align_completed_to_base(values, timeframe="1h", base_index=frame.index).to_numpy()
    hour_oi = frame["open_interest"].resample("1h").last().to_numpy()
    hourly = _loop(hour_oi, 5, "rolling_max")
    hours = (frame.index.asi8 - frame.index.asi8[0]) // 3_600_000_000_000
    expected = np.where(hours >= 1, hourly[np.maximum(hours - 1, 0)], math.nan)
    np.testing.assert_array_equal(got, expected)


def test_request_label_identity_and_validation() -> None:
    feature = plan_feature_request("rolling_max", None, "open_interest", {"period": 8640})
    assert feature.output_id == "rolling_max_open_interest_base_8640"
    close = plan_feature_request("rolling_max", None, None, {"period": 8640})
    assert close.output_id == "rolling_max_close_base_8640"
    by_oi = resolve_feature(feature, base_timeframe="5m", upstream={})
    by_close = resolve_feature(close, base_timeframe="5m", upstream={})
    assert by_oi != by_close
    for source, params in (
        ("volume", {"period": 3}),
        ("close", {"period": 0}),
        ("close", {"period": 3, "extra": 1}),
        ("close", {}),
    ):
        with pytest.raises(InvalidRequestError):
            plan_feature_request("rolling_min", None, source, params)


def test_live_warm_up_is_the_period() -> None:
    from strategy_engine.strategies.live_calculation.indicator_requirements import (
        _FINITE_KINDS,
    )

    assert {"rolling_max", "rolling_min"} <= _FINITE_KINDS


def test_open_interest_is_a_base_bar_field_operand() -> None:
    operand = _parse({"price": "open_interest"}).long.operand
    assert operand.price == "open_interest"
    oi = [Decimal("100.5"), None, Decimal("101")]
    bars = tuple(
        MarketBar(
            i * 300_000,
            Decimal("1"),
            Decimal("2"),
            Decimal("0.5"),
            Decimal("1.5"),
            Decimal("1"),
            oi[i],
        )
        for i in range(3)
    )
    frame = SimpleNamespace(market_arrays=MarketArrays(tuple(b.open_time_ms for b in bars), bars))
    got = _values(operand, frame, None, None, "long", None)  # type: ignore[arg-type]
    np.testing.assert_array_equal(np.asarray(got), [100.5, math.nan, 101.0])
    with pytest.raises(InvalidRequestError):
        _parse({"price": "volume"})
