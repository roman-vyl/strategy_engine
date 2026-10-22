"""How much of the impulse the pullback gave back (OpenSpec
`c3-pullback-depth-share-v1`): `g * (peak_price - ext[t]) / |peak_price -
origin_price|` for the current touch of an EMA stack episode, `ext[t]` the
lowest low (long) or highest high (short) of the bars `[P, t]`, `g` +1 on the
long side and -1 on the short side."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.anchor_follow import _touch_rows
from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode


def pullback_depth_values(episode: SideEpisode, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """The C3.1 value on every bar as a read-only float64 array; missing where
    the touch has no valid wave, the impulse height is 0 or a price of
    `[P, t]` is not finite. Nothing after the evaluated bar is read."""

    size = len(episode.state["touch_number"])
    out = np.full(size, math.nan)
    valid, _, peak = touch_points(episode, size)
    if len(episode.touches["peak_price"]) == 0 or not valid.any():
        out.flags.writeable = False
        return out
    long = episode.side == "long"
    g = 1.0 if long else -1.0
    rows = _touch_rows(episode, size)
    peak_price = episode.touches["peak_price"][rows]
    origin_price = episode.touches["origin_price"][rows]
    prices = np.asarray(low if long else high, dtype=np.float64)
    pick = min if long else max
    prev_peak, prev_t, ext = -1, -1, math.nan
    for t in np.flatnonzero(valid):
        p = int(peak[t])
        if p == prev_peak and t == prev_t + 1:
            price = float(prices[t])
            ext = pick(ext, price) if math.isfinite(ext) and math.isfinite(price) else math.nan
        else:
            window = prices[p : t + 1]
            ext = float(window.min() if long else window.max())
        prev_peak, prev_t = p, int(t)
        height = abs(float(peak_price[t]) - float(origin_price[t]))
        if math.isfinite(ext) and height > 0.0:
            out[t] = g * (float(peak_price[t]) - ext) / height
    out.flags.writeable = False
    return out
