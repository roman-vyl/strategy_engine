"""D1 forming candle operand (OpenSpec `d1-forming-candle-v1`): parsing, the value
`g * (close[t] - open of the forming candle) / atr` against a loop written like the
research reference (`altvals.py` `tf_frame`, `d1`), missing cases and no look-ahead."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.forming_candle import forming_candle_values

ATR = {"kind": "atr_wilder", "timeframe": "1h", "params": {"period": 14}}
BASE_MS = 300_000
HOUR_MS = 3_600_000


def _operand(**fields: Any) -> dict[str, Any]:
    return {"forming_candle": {"episode": "trend", "timeframe": "1h", "atr": ATR, **fields}}


def reference(
    episode: Any,
    time_ms: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    tf: int,
) -> np.ndarray:
    g = 1.0 if episode.side == "long" else -1.0
    out = np.full(len(time_ms), math.nan)
    for t in range(len(time_ms)):
        legs = _legs(episode, t)
        if legs is None or not (legs[0] <= legs[1] <= t):
            continue
        first = t
        while first > 0 and time_ms[first - 1] // tf == time_ms[t] // tf:
            first -= 1
        if math.isfinite(atr[t]) and atr[t] > 0:
            out[t] = g * (close[t] - open_[first]) / atr[t]
    return out


def _series(size: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    time_ms = 7 * BASE_MS + np.arange(size, dtype=np.int64) * BASE_MS  # starts mid-hour
    open_ = 100 + rng.normal(0, 1, size)
    close = open_ + rng.normal(0, 0.5, size)
    atr = rng.uniform(0.2, 1.5, size)
    atr[:20] = math.nan  # ATR warm-up
    return time_ms, open_, close, atr


def test_forming_candle_parses_as_a_range_and_ratio_operand() -> None:
    operand = _parse(_operand()).long.operand.forming_candle
    assert operand.episode == "trend" and operand.timeframe == "1h"
    assert operand.atr.kind == "atr_wilder" and operand.atr.timeframe == "1h"
    ratio = {"ratio": {"left": _operand(), "right": {"const": 2.0}}}
    assert _parse(ratio).long.operand.ratio.left.forming_candle.timeframe == "1h"


@pytest.mark.parametrize(
    "fields",
    [
        {"atr": {"kind": "atr", "timeframe": "1h", "params": {"period": 14}}},
        {"atr": {"kind": "atr_wilder", "timeframe": "4h", "params": {"period": 14}}},
        {"atr": {"kind": "atr_wilder", "params": {"period": 14}}},
        {"timeframe": "base"},
        {"timeframe": ""},
        {"episode": "other"},
        {"extra": 1},
    ],
)
def test_malformed_forming_candle_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_operand(**fields))


@pytest.mark.parametrize("missing", ["episode", "timeframe", "atr"])
def test_required_fields(missing: str) -> None:
    operand = _operand()
    del operand["forming_candle"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_forming_candle_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
def test_forming_candle_matches_the_loop(seed: int, side: str) -> None:
    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    time_ms, open_, close, atr = _series(size, seed)
    got = forming_candle_values(
        episode, time_ms=time_ms, open_=open_, close=close, timeframe_ms=HOUR_MS, atr=atr
    )
    expected = reference(episode, time_ms, open_, close, atr, HOUR_MS)
    np.testing.assert_allclose(got, expected, rtol=1e-12, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable


def test_day_moved_against_a_long() -> None:
    episode, size, _ = _episode_bars(1)
    valid = np.flatnonzero(
        [(lg := _legs(episode, t)) is not None and lg[0] <= lg[1] <= t for t in range(size)]
    )
    t = int(valid[len(valid) // 2])
    time_ms = np.arange(size, dtype=np.int64) * BASE_MS
    open_ = np.full(size, 100.0)
    close = np.full(size, 98.0)
    atr = np.full(size, 4.0)
    for side, value in (("long", -0.5), ("short", 0.5)):
        got = forming_candle_values(
            dataclasses.replace(episode, side=side),
            time_ms=time_ms,
            open_=open_,
            close=close,
            timeframe_ms=HOUR_MS,
            atr=atr,
        )
        assert got[t] == value


def test_missing_without_atr_or_wave() -> None:
    episode, size, _ = _episode_bars(3)
    time_ms, open_, close, _ = _series(size, 3)
    for atr in (np.full(size, math.nan), np.zeros(size)):
        got = forming_candle_values(
            episode, time_ms=time_ms, open_=open_, close=close, timeframe_ms=HOUR_MS, atr=atr
        )
        assert np.isnan(got).all()
    got = forming_candle_values(
        episode, time_ms=time_ms, open_=open_, close=close, timeframe_ms=HOUR_MS, atr=np.ones(size)
    )
    no_wave = [t for t in range(size) if _legs(episode, t) is None]
    assert no_wave and np.isnan(got[no_wave]).all()


def test_no_look_ahead() -> None:
    episode, size, _ = _episode_bars(2)
    time_ms, open_, close, atr = _series(size, 2)
    full = forming_candle_values(
        episode, time_ms=time_ms, open_=open_, close=close, timeframe_ms=HOUR_MS, atr=atr
    )
    for cut in (size // 3, size // 2, size - 5):
        o, c, a = open_.copy(), close.copy(), atr.copy()
        o[cut + 1 :], c[cut + 1 :], a[cut + 1 :] = 1e9, -1e9, 1e-9
        got = forming_candle_values(
            episode, time_ms=time_ms, open_=o, close=c, timeframe_ms=HOUR_MS, atr=a
        )
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])
