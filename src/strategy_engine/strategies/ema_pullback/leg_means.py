"""Mean of a base-bar market field over a leg of the current touch of an EMA
stack episode (OpenSpec `v1-volume-ratio-v1`): the impulse `[S*, P]` or the
pullback `[P + 1, t]`, both ends inclusive. Prefix sums, O(bars)."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

LEG_MEAN_FIELDS = ("volume",)


def leg_mean_values(episode: SideEpisode, series: np.ndarray, leg: str) -> np.ndarray:
    """The leg mean on every bar as a read-only float64 array; missing where
    the touch has no valid wave, the leg is empty or a bar of it is not finite."""

    size = len(series)
    valid, origin, peak = touch_points(episode, size)
    current = np.arange(size)
    if leg == "impulse":
        begin, end = origin, peak
    else:
        begin, end = peak + 1, current
        valid = valid & (begin <= end)
    begin = np.where(valid, begin, 0)
    end = np.where(valid, end, 0)
    finite = np.isfinite(series)
    bad = np.zeros(size + 1, dtype=np.int64)
    np.cumsum(~finite, out=bad[1:])
    total = np.zeros(size + 1)
    np.cumsum(np.where(finite, series, 0.0), out=total[1:])
    valid = valid & ((bad[end + 1] - bad[begin]) == 0)
    mean = (total[end + 1] - total[begin]) / (end - begin + 1)
    out = np.where(valid, mean, math.nan)
    out.flags.writeable = False
    return out
