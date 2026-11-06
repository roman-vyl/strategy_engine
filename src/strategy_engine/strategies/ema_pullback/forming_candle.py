"""Where the forming higher-timeframe candle stands (OpenSpec
`d1-forming-candle-v1`): `g * (close[t] - open) / atr`, `open` the open of
the first base bar of the candle of the timeframe that contains `t`, `atr`
the Wilder ATR of the last completed candle (the aligned feature value), `g`
+1 on the long side and -1 on the short side; only on bars with a valid wave
of the current touch, as research computes D1 on entries."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

FORMING_CANDLE_ATR_FIELD = "atr"  # the wire name of the normalising feature
FORMING_CANDLE_ATR_KIND = "atr_wilder"  # Wilder, as the research reference


def forming_candle_values(
    episode: SideEpisode,
    *,
    time_ms: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    timeframe_ms: int,
    atr: np.ndarray,
    field: str = "body",
    high: np.ndarray | None = None,
    low: np.ndarray | None = None,
    base_ms: int | None = None,
) -> np.ndarray:
    """The value on every bar as a read-only float64 array; missing without a
    valid wave, a finite price or a positive ATR. Nothing after `t` is read."""

    if field == "range":
        if high is None or low is None or base_ms is None:
            raise ValueError("range requires high, low and base_ms")
        result = forming_range_values(time_ms, high, low, atr, timeframe_ms, base_ms)
        result = np.where(touch_points(episode, len(time_ms))[0], result, np.nan)
        result.flags.writeable = False
        return result
    size = len(time_ms)
    out = np.full(size, math.nan)
    if size:
        bucket = np.asarray(time_ms, dtype=np.int64) // timeframe_ms
        starts = np.concatenate(([True], bucket[1:] != bucket[:-1]))
        first_bar = np.flatnonzero(starts)[np.cumsum(starts) - 1]
        g = 1.0 if episode.side == "long" else -1.0
        valid, _, _ = touch_points(episode, size)
        atr = np.asarray(atr, dtype=np.float64)
        with np.errstate(invalid="ignore"):
            usable = valid & np.isfinite(atr) & (atr > 0)
        rows = np.flatnonzero(usable)
        out[rows] = g * (close[rows] - open_[first_bar[rows]]) / atr[rows]
    out.flags.writeable = False
    return out


def forming_range_values(
    time_ms: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    timeframe_ms: int,
    base_ms: int,
) -> np.ndarray:
    """Observed range / prior bucket ATR aligned at base OPEN, never close.

    Freeze the aligned ATR at bucket start. Invalid/gapped prefixes remain
    missing until the next complete bucket.
    """
    out = np.full(len(time_ms), np.nan)
    previous_bucket = -1
    valid = False
    hi = lo = denominator = math.nan
    for i, stamp in enumerate(time_ms):
        bucket = int(stamp) // timeframe_ms
        if bucket != previous_bucket:
            valid = int(stamp) % timeframe_ms == 0
            hi, lo, denominator = -math.inf, math.inf, float(atr[i])
        elif i and stamp - time_ms[i - 1] != base_ms:
            valid = False
        previous_bucket = bucket
        valid = valid and math.isfinite(high[i]) and math.isfinite(low[i])
        if valid:
            hi, lo = max(hi, high[i]), min(lo, low[i])
            if math.isfinite(denominator) and denominator > 0:
                out[i] = (hi - lo) / denominator
    out.flags.writeable = False
    return out
