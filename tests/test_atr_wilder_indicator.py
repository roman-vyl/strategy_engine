"""`atr_wilder` feature (OpenSpec `b1-candle-ratio-v1`, task 1.4): the research
reference's Wilder ATR, seed and recursion."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.indicators.implementations.atr import atr_rolling_mean, atr_wilder


def _bars(size: int, seed: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, size))
    high = close + rng.uniform(0.1, 2, size)
    low = close - rng.uniform(0.1, 2, size)
    return pd.Series(high), pd.Series(low), pd.Series(close)


def _reference(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    """First TR is high - low, seed is the mean of the first n TR, then
    (atr * (n - 1) + tr) / n."""

    tr = np.empty(len(high))
    tr[0] = high[0] - low[0]
    for i in range(1, len(high)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.full(len(high), np.nan)
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(high)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


@pytest.mark.parametrize("period", [1, 5, 14])
def test_matches_the_reference_loop(period: int) -> None:
    high, low, close = _bars(200, 4)
    got = atr_wilder(high, low, close, period=period).to_numpy()
    expected = _reference(high.to_numpy(), low.to_numpy(), close.to_numpy(), period)
    np.testing.assert_allclose(got, expected, rtol=1e-12, equal_nan=True)
    assert np.isnan(got[: period - 1]).all() and np.isfinite(got[period - 1 :]).all()


def test_short_series_is_missing_and_sma_atr_is_unchanged() -> None:
    high, low, close = _bars(10, 1)
    assert atr_wilder(high, low, close, period=14).isna().all()
    sma = atr_rolling_mean(high, low, close, period=3)
    assert np.isnan(sma.iloc[1]) and np.isfinite(sma.iloc[2])


def test_label_and_kind_contract() -> None:
    feature = plan_feature_request("atr_wilder", "15m", None, {"period": 14})
    assert feature.output_id == "atr_wilder_close_15m_14" and feature.source == "close"
    with pytest.raises(Exception, match="period"):
        plan_feature_request("atr_wilder", None, None, {"period": 0})
