"""Price distance per bar of a leg of the current touch (OpenSpec
`a3-leg-speed-ratio-v1`): the impulse `|peak_price - origin_price| / (P - S* + 1)`
and the pullback `|peak_price - close[t]| / (t - P + 1)`, the bar `P` counted in
both legs as in research. A3 is the ratio of the two."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.anchor_follow import _touch_rows
from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode


def leg_speed_values(episode: SideEpisode, close: np.ndarray, leg: str) -> np.ndarray:
    """The leg speed on every bar as a read-only float64 array; missing where
    the touch has no valid wave or an input price is not finite. Only the close
    of the evaluated bar is read."""

    size = len(episode.state["touch_number"])
    out = np.full(size, math.nan)
    valid, origin, peak = touch_points(episode, size)
    if len(episode.touches["peak_price"]) == 0 or not valid.any():
        out.flags.writeable = False
        return out
    rows = _touch_rows(episode, size)
    peak_price = episode.touches["peak_price"][rows]
    if leg == "impulse":
        distance = np.abs(peak_price - episode.touches["origin_price"][rows])
        bars = peak - origin + 1
    else:
        distance = np.abs(peak_price - np.asarray(close, dtype=np.float64))
        bars = np.arange(size) - peak + 1
    with np.errstate(invalid="ignore"):
        ok = valid & np.isfinite(distance)
    out[ok] = distance[ok] / bars[ok]
    out.flags.writeable = False
    return out
