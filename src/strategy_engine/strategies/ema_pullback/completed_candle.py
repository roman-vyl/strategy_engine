"""The last completed higher-timeframe candle (OpenSpec
`completed-candle-v1`): its body `g * (close - open) / atr` or the position of
its close in its range, `g` +1 on the long side and -1 on the short side,
`atr` the Wilder ATR of the candle before it (the aligned feature value on
the last base bar of the completed candle). Candles are built from the base
bars: UTC days (or divisors of a day) and weeks from Monday 00:00 UTC. Only on
bars with a valid wave of the current touch, as research computes D1v and Wk
on entries."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

COMPLETED_CANDLE_ATR_FIELD = "atr"  # the wire name of the normalising feature
COMPLETED_CANDLE_ATR_KIND = "atr_wilder"  # Wilder, as the research reference
COMPLETED_CANDLE_FIELDS = ("body", "close_position")

_DAY_MS = 86_400_000
_WEEK_MS = 7 * _DAY_MS
# The epoch day 0 is a Thursday: shifting by three days starts weeks on Monday.
_WEEK_SHIFT_MS = 3 * _DAY_MS


def candle_buckets(time_ms: np.ndarray, timeframe_ms: int) -> np.ndarray:
    """The candle number of every base bar: UTC days or divisors of a day by
    plain division, weeks from Monday 00:00 UTC."""

    time_ms = np.asarray(time_ms, dtype=np.int64)
    if timeframe_ms % _WEEK_MS == 0:
        return (time_ms + _WEEK_SHIFT_MS) // timeframe_ms
    return time_ms // timeframe_ms


def completed_candle_values(
    episode: SideEpisode,
    *,
    time_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    timeframe_ms: int,
    field: str,
    atr: np.ndarray,
) -> np.ndarray:
    """The value on every bar as a read-only float64 array; missing without a
    valid wave, before the first completed candle, without a finite price, a
    positive ATR (body) or a positive range (close position). Nothing after
    `t` is read: the completed candle ends before the candle of `t`."""

    size = len(time_ms)
    out = np.full(size, math.nan)
    if size:
        bucket = candle_buckets(time_ms, timeframe_ms)
        first = np.concatenate(([True], bucket[1:] != bucket[:-1]))
        starts = np.flatnonzero(first)
        number = np.cumsum(first) - 1  # the candle of each bar
        ends = np.concatenate((starts[1:], [size])) - 1
        with np.errstate(invalid="ignore"):
            c_open = open_[starts]
            c_close = close[ends]
            c_high = np.maximum.reduceat(high, starts)
            c_low = np.minimum.reduceat(low, starts)
        g = 1.0 if episode.side == "long" else -1.0
        valid, _, _ = touch_points(episode, size)
        rows = np.flatnonzero(valid & (number >= 1))
        prev = number[rows] - 1
        if field == "body":
            # The aligned ATR on the last base bar of the completed candle is
            # the ATR of the candle before it.
            scale = np.asarray(atr, dtype=np.float64)[ends[prev]]
            value = g * (c_close[prev] - c_open[prev])
        else:
            scale = c_high[prev] - c_low[prev]
            value = c_close[prev] - c_low[prev] if g > 0 else c_high[prev] - c_close[prev]
        with np.errstate(invalid="ignore", divide="ignore"):
            usable = np.isfinite(scale) & (scale > 0) & np.isfinite(value)
            out[rows[usable]] = value[usable] / scale[usable]
    out.flags.writeable = False
    return out
