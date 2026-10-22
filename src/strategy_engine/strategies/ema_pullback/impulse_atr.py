"""Impulse height in average candles (OpenSpec `b3-impulse-atr-v1`):
`|peak_price - origin_price| / atr[P]` for the current touch of an EMA stack
episode, `atr` the rolling-mean true range read on the peak bar `P`."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.anchor_follow import _touch_rows
from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

IMPULSE_ATR_FIELD = "atr"  # the wire name of the normalising feature
IMPULSE_ATR_KIND = "atr"  # rolling-mean true range, as the research reference


def impulse_atr_values(episode: SideEpisode, atr: np.ndarray) -> np.ndarray:
    """The B3 value on every bar as a read-only float64 array; missing where
    the touch has no valid wave, a price is not finite or `atr[P]` is not
    finite or not above 0. `P <= t`, so nothing after `t` is read."""

    size = len(episode.state["touch_number"])
    out = np.full(size, math.nan)
    valid, _, peak = touch_points(episode, size)
    if len(episode.touches["peak_price"]) == 0 or not valid.any():
        out.flags.writeable = False
        return out
    rows = _touch_rows(episode, size)
    height = np.abs(episode.touches["peak_price"][rows] - episode.touches["origin_price"][rows])
    scale = np.asarray(atr, dtype=np.float64)[peak]
    with np.errstate(invalid="ignore"):
        ok = valid & np.isfinite(height) & np.isfinite(scale) & (scale > 0.0)
    out[ok] = height[ok] / scale[ok]
    out.flags.writeable = False
    return out
