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
) -> np.ndarray:
    """The value on every bar as a read-only float64 array; missing without a
    valid wave, a finite price or a positive ATR. Nothing after `t` is read."""

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
