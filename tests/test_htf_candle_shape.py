"""Candle shape features (OpenSpec `htf-candle-shape-v1`): `candle_body_atr` and
`candle_close_position` on a higher timeframe, computed on its own candles and
aligned to the base bars as the value of the last completed candle, against a loop
written like the research reference (`combo3.py` `days`, `week.py` `weeks`). The range
evaluator branch is exercised end to end by the EMA200 parity run."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.indicators.implementations.frame_ops import (
    align_completed_to_base,
    resample_ohlcv,
)
from strategy_engine.indicators.implementations.range_evaluator import resolve_feature

DAY_MS = 86_400_000


def _frame(days: int, seed: int, step: str = "1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-03 05:00", periods=days * 24, freq=step, tz="UTC")  # Wednesday
    o = 100 + np.cumsum(rng.normal(0, 1, len(index)))
    c = o + rng.normal(0, 0.8, len(index))
    h = np.maximum(o, c) + rng.uniform(0, 0.5, len(index))
    lo = np.minimum(o, c) - rng.uniform(0, 0.5, len(index))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1.0}, index=index)


def _reference(frame: pd.DataFrame, week: bool, period: int = 14) -> dict[str, np.ndarray]:
    """Research: candles by UTC day (weeks from Monday), Wilder ATR seeded with the
    mean of the first `period` true ranges; for a base bar in candle kk the value
    of candle p = kk - 1, the body over atr[p - 1]."""

    t = frame.index.asi8 // 1_000_000
    o, h, lo, cl = (frame[k].to_numpy() for k in ("open", "high", "low", "close"))
    g_ = (t // DAY_MS + 3) // 7 if week else t // DAY_MS
    first = np.r_[True, g_[1:] != g_[:-1]]
    idx = np.cumsum(first) - 1
    k = idx.max() + 1
    kh = np.full(k, -np.inf)
    kl = np.full(k, np.inf)
    kc = np.zeros(k)
    np.maximum.at(kh, idx, h)
    np.minimum.at(kl, idx, lo)
    kc[idx] = cl
    ko = o[first]
    pc = np.r_[np.nan, kc[:-1]]
    tr = np.nanmax(np.c_[kh - kl, np.abs(kh - pc), np.abs(kl - pc)], axis=1)
    atr = np.full(k, np.nan)
    atr[period - 1] = np.nanmean(tr[:period])
    for i in range(period, k):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    p = idx - 1
    ok = p >= 0
    body = np.full(len(t), math.nan)
    pos = np.full(len(t), math.nan)
    a = np.where(p >= 1, atr[np.maximum(p - 1, 0)], np.nan)
    body[ok] = (kc[p[ok]] - ko[p[ok]]) / a[ok]
    pos[ok] = (kc[p[ok]] - kl[p[ok]]) / (kh[p[ok]] - kl[p[ok]])
    return {"body": body, "pos": pos}


def _engine(frame: pd.DataFrame, kind: str, timeframe: str) -> np.ndarray:
    htf = resample_ohlcv(frame, timeframe)
    from strategy_engine.indicators.implementations import range_evaluator as re_

    values = {
        "candle_body_atr": lambda: re_.candle_body_atr(htf, period=14),
        "candle_close_position": lambda: re_.candle_close_position(htf),
    }[kind]()
    return align_completed_to_base(values, timeframe=timeframe, base_index=frame.index).to_numpy()


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize(("timeframe", "week", "days"), [("1d", False, 60), ("1w", True, 210)])
def test_values_match_the_research_loop(seed: int, timeframe: str, week: bool, days: int) -> None:
    frame = _frame(days, seed)
    ref = _reference(frame, week)
    body = _engine(frame, "candle_body_atr", timeframe)
    pos = _engine(frame, "candle_close_position", timeframe)
    np.testing.assert_allclose(body, ref["body"], rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(pos, ref["pos"], rtol=1e-12, equal_nan=True)
    assert np.isfinite(body).sum() > 100 and np.isnan(body[:24]).all()


def test_strong_yesterday() -> None:
    index = pd.date_range("2024-01-01", periods=24 * 20, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}, index=index
    )
    day = frame.index.normalize() == pd.Timestamp("2024-01-18", tz="UTC")
    frame.loc[day, ["high", "low"]] = [105.0, 95.0]
    frame.loc[frame.index[day][0], "open"] = 100.0
    frame.loc[frame.index[day][-1], "close"] = 104.0
    htf = resample_ohlcv(frame, "1d")
    from strategy_engine.indicators.implementations import range_evaluator as re_

    body = align_completed_to_base(
        re_.candle_body_atr(htf, period=14), timeframe="1d", base_index=index
    )
    pos = align_completed_to_base(re_.candle_close_position(htf), timeframe="1d", base_index=index)
    at = index.get_loc(pd.Timestamp("2024-01-19 10:00", tz="UTC"))
    assert body.iloc[at] == pytest.approx(4.0 / 2.0)  # the ATR of the day before is 2
    assert pos.iloc[at] == pytest.approx(0.9)


def test_flat_candle_has_no_close_position() -> None:
    index = pd.date_range("2024-01-01", periods=48, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=index
    )
    from strategy_engine.indicators.implementations import range_evaluator as re_

    assert re_.candle_close_position(resample_ohlcv(frame, "1d")).isna().all()


@pytest.mark.parametrize(
    ("kind", "params", "source"),
    [
        ("candle_body_atr", {}, None),
        ("candle_body_atr", {"period": 0}, None),
        ("candle_body_atr", {"period": 14}, "open"),
        ("candle_close_position", {"period": 14}, None),
        ("candle_close_position", {}, "open"),
    ],
)
def test_malformed_requests_are_rejected(kind: str, params: dict, source: str | None) -> None:
    with pytest.raises(InvalidRequestError):
        plan_feature_request(kind, "1d", source, params)


def test_identity_carries_kind_timeframe_and_period() -> None:
    body = plan_feature_request("candle_body_atr", "1d", None, {"period": 14})
    pos = plan_feature_request("candle_close_position", "1w", None, {})
    assert body.output_id == "candle_body_atr_close_1d_14"
    assert pos.output_id == "candle_close_position_1w"
    a = resolve_feature(body, base_timeframe="5m", upstream={})
    b = resolve_feature(pos, base_timeframe="5m", upstream={})
    assert a != b


def test_weekly_feature_frame_starts_on_monday() -> None:
    index = pd.date_range("2024-01-01", periods=24 * 21, freq="h", tz="UTC")  # a Monday
    frame = pd.DataFrame(
        {
            "open": np.arange(len(index), dtype=float),
            "high": 1e9,
            "low": 0.0,
            "close": np.arange(len(index), dtype=float),
            "volume": 1.0,
        },
        index=index,
    )
    weekly = resample_ohlcv(frame, "1w")
    assert list(weekly.index.dayofweek) == [0, 0, 0]
    assert weekly["open"].tolist() == [0.0, 168.0, 336.0]
    aligned = align_completed_to_base(weekly["close"], timeframe="1w", base_index=index)
    assert math.isnan(aligned.iloc[167])  # the first week is not completed yet
    assert aligned.iloc[168] == 167.0 and aligned.iloc[335] == 167.0 and aligned.iloc[336] == 335.0


def test_live_warm_up() -> None:
    from strategy_engine.indicators.contracts import IndicatorPlan
    from strategy_engine.strategies.live_calculation.indicator_requirements import (
        ResolveIndicatorHistoryRequirements,
    )

    features = (
        plan_feature_request("atr_wilder", "1d", None, {"period": 14}),
        plan_feature_request("candle_body_atr", "1d", None, {"period": 14}),
        plan_feature_request("candle_close_position", "1d", None, {}),
    )
    atr, body, pos = ResolveIndicatorHistoryRequirements().execute(IndicatorPlan("v1", features))
    assert body.bars == atr.bars + 1 and body.timeframe == "1d"
    assert pos.bars == 1 and pos.timeframe == "1d"
