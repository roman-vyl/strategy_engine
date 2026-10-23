"""Completed candle operand (OpenSpec `completed-candle-v1`): parsing, the body
`g * (close - open) / atr of the candle before` and the close position of the last
completed candle against a loop written like the research reference
(`combo3.py` `days`, `week.py` `weeks`), weeks from Monday, missing cases and no
look-ahead; the weekly feature frame starts weeks on Monday."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.implementations.frame_ops import (
    align_completed_to_base,
    resample_ohlcv,
)
from strategy_engine.strategies.ema_pullback.completed_candle import (
    candle_buckets,
    completed_candle_values,
)

ATR = {"kind": "atr_wilder", "timeframe": "1h", "params": {"period": 14}}
BASE_MS = 300_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS


def _operand(**fields: Any) -> dict[str, Any]:
    return {
        "completed_candle": {
            "episode": "trend",
            "timeframe": "1h",
            "field": "body",
            "atr": ATR,
            **fields,
        }
    }


def _bucket(time: int, tf: int) -> int:
    if tf % WEEK_MS == 0:
        return (time // DAY_MS + 3) // 7 if tf == WEEK_MS else -1
    return time // tf


def reference(
    episode: Any,
    time_ms: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    lo: np.ndarray,
    c: np.ndarray,
    atr: np.ndarray,
    tf: int,
    field: str,
) -> np.ndarray:
    g = 1.0 if episode.side == "long" else -1.0
    out = np.full(len(time_ms), math.nan)
    for t in range(len(time_ms)):
        legs = _legs(episode, t)
        if legs is None or not (legs[0] <= legs[1] <= t):
            continue
        first = t
        while first > 0 and _bucket(time_ms[first - 1], tf) == _bucket(time_ms[t], tf):
            first -= 1
        if first == 0:
            continue
        end = first - 1
        start = end
        while start > 0 and _bucket(time_ms[start - 1], tf) == _bucket(time_ms[end], tf):
            start -= 1
        hi, low = h[start : end + 1].max(), lo[start : end + 1].min()
        if field == "body":
            if math.isfinite(atr[end]) and atr[end] > 0:
                out[t] = g * (c[end] - o[start]) / atr[end]
        elif hi > low:
            out[t] = (c[end] - low if g > 0 else hi - c[end]) / (hi - low)
    return out


def _series(size: int, seed: int, step: int = BASE_MS) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    time_ms = 7 * step + np.arange(size, dtype=np.int64) * step  # starts mid-candle
    o = 100 + rng.normal(0, 1, size)
    c = o + rng.normal(0, 0.5, size)
    h = np.maximum(o, c) + rng.uniform(0, 0.5, size)
    lo = np.minimum(o, c) - rng.uniform(0, 0.5, size)
    atr = rng.uniform(0.2, 1.5, size)
    atr[:20] = math.nan  # ATR warm-up
    return time_ms, o, h, lo, c, atr


def _values(episode: Any, series: tuple[np.ndarray, ...], tf: int, field: str) -> np.ndarray:
    time_ms, o, h, lo, c, atr = series
    return completed_candle_values(
        episode,
        time_ms=time_ms,
        open_=o,
        high=h,
        low=lo,
        close=c,
        timeframe_ms=tf,
        field=field,
        atr=atr,
    )


def test_completed_candle_parses_as_a_range_and_ratio_operand() -> None:
    operand = _parse(_operand(field="close_position")).long.operand.completed_candle
    assert operand.episode == "trend" and operand.timeframe == "1h"
    assert operand.field == "close_position" and operand.atr.kind == "atr_wilder"
    ratio = {"ratio": {"left": _operand(), "right": {"const": 2.0}}}
    assert _parse(ratio).long.operand.ratio.left.completed_candle.field == "body"


@pytest.mark.parametrize(
    "fields",
    [
        {"atr": {"kind": "atr", "timeframe": "1h", "params": {"period": 14}}},
        {"atr": {"kind": "atr_wilder", "timeframe": "4h", "params": {"period": 14}}},
        {"timeframe": "base"},
        {"field": "range"},
        {"episode": "other"},
        {"extra": 1},
    ],
)
def test_malformed_completed_candle_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_operand(**fields))


@pytest.mark.parametrize("missing", ["episode", "timeframe", "field", "atr"])
def test_required_fields(missing: str) -> None:
    operand = _operand()
    del operand["completed_candle"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_completed_candle_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("field", ["body", "close_position"])
@pytest.mark.parametrize(("step", "tf"), [(BASE_MS, HOUR_MS), (DAY_MS // 4, WEEK_MS)])
def test_completed_candle_matches_the_loop(
    seed: int, side: str, field: str, step: int, tf: int
) -> None:
    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    series = _series(size, seed, step)
    got = _values(episode, series, tf, field)
    expected = reference(episode, *series, tf, field)
    np.testing.assert_allclose(got, expected, rtol=1e-12, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable


def test_weeks_start_on_monday() -> None:
    monday = int(pd.Timestamp("2024-01-01", tz="UTC").value // 1_000_000)
    times = np.array([monday - 1, monday, monday + WEEK_MS - 1, monday + WEEK_MS])
    buckets = candle_buckets(times, WEEK_MS)
    assert buckets[0] != buckets[1] == buckets[2] != buckets[3]


def test_yesterday_body_and_close_position() -> None:
    episode, size, _ = _episode_bars(1)
    valid = np.flatnonzero(
        [(lg := _legs(episode, t)) is not None and lg[0] <= lg[1] <= t for t in range(size)]
    )
    t = int(valid[len(valid) // 2])
    time_ms = np.arange(size, dtype=np.int64) * BASE_MS
    first = t - (time_ms[t] % HOUR_MS) // BASE_MS  # first bar of the candle of t
    o, h, lo, c = (np.full(size, 100.0) for _ in range(4))
    start = first - 12
    o[start], c[first - 1] = 100.0, 104.0
    h[start:first], lo[start:first] = 105.0, 95.0
    atr = np.full(size, 8.0)
    atr[first - 1] = 2.0  # the ATR of the candle before the completed one
    series = (time_ms, o, h, lo, c, atr)
    for side, body, pos in (("long", 2.0, 0.9), ("short", -2.0, 0.1)):
        ep = dataclasses.replace(episode, side=side)
        assert _values(ep, series, HOUR_MS, "body")[t] == body
        assert _values(ep, series, HOUR_MS, "close_position")[t] == pytest.approx(pos)


def test_missing_without_atr_range_or_wave() -> None:
    episode, size, _ = _episode_bars(3)
    time_ms, o, h, lo, c, _ = _series(size, 3)
    for atr in (np.full(size, math.nan), np.zeros(size)):
        assert np.isnan(_values(episode, (time_ms, o, h, lo, c, atr), HOUR_MS, "body")).all()
    flat = np.full(size, 100.0)
    got = _values(
        episode, (time_ms, flat, flat, flat, flat, np.ones(size)), HOUR_MS, "close_position"
    )
    assert np.isnan(got).all()
    got = _values(episode, (time_ms, o, h, lo, c, np.ones(size)), HOUR_MS, "body")
    no_wave = [t for t in range(size) if _legs(episode, t) is None]
    assert no_wave and np.isnan(got[no_wave]).all()
    head = time_ms < (time_ms[0] // HOUR_MS + 1) * HOUR_MS  # the first candle
    assert np.isnan(got[head]).all()


@pytest.mark.parametrize("field", ["body", "close_position"])
def test_no_look_ahead(field: str) -> None:
    episode, size, _ = _episode_bars(2)
    series = _series(size, 2)
    full = _values(episode, series, HOUR_MS, field)
    for cut in (size // 3, size // 2, size - 5):
        changed = [a.copy() for a in series]
        for a, v in zip(changed[1:], (1e9, 1e9, -1e9, -1e9, 1e-9), strict=True):
            a[cut + 1 :] = v
        got = _values(episode, tuple(changed), HOUR_MS, field)
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


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
    assert aligned.iloc[167] != aligned.iloc[167]  # the first week is not completed yet
    assert aligned.iloc[168] == 167.0 and aligned.iloc[335] == 167.0 and aligned.iloc[336] == 335.0
