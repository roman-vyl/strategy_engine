"""Kaufman efficiency ratio of the closes of a leg of the current touch
(OpenSpec `a5-leg-efficiency-ratio-v1`): `|close[z] - close[a]| / sum of
|close[k] - close[k-1]|` over `k = a+1..z`, the impulse `a = S*, z = P` and
the pullback `a = P, z = t`. A5 is the ratio of the two."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode


def leg_efficiency_values(episode: SideEpisode, close: np.ndarray, leg: str) -> np.ndarray:
    """The leg efficiency on every bar as a read-only float64 array; missing
    where the touch has no valid wave, the leg has one bar, the closes do not
    move or a close of the leg is not finite. Nothing after `t` is read."""

    size = len(episode.state["touch_number"])
    out = np.full(size, math.nan)
    valid, origin, peak = touch_points(episode, size)
    if size == 0 or not valid.any():
        out.flags.writeable = False
        return out
    close = np.asarray(close, dtype=np.float64)
    finite = np.isfinite(close)
    step = np.zeros(size)
    step[1:] = np.abs(np.diff(np.where(finite, close, 0.0)))
    path = np.cumsum(step)  # path[z] - path[a] = sum over k = a+1..z
    bad = np.cumsum(~finite)  # non-finite closes up to each bar
    if leg == "impulse":
        a, z = origin, peak
    else:
        a, z = peak, np.arange(size)
    a, z = np.where(valid, a, 0), np.where(valid, z, 0)
    run = path[z] - path[a]
    clean = bad[z] - np.where(a > 0, bad[np.maximum(a - 1, 0)], 0) == 0
    ok = valid & (z > a) & clean & (run > 0)
    out[ok] = np.abs(close[z[ok]] - close[a[ok]]) / run[ok]
    out.flags.writeable = False
    return out
