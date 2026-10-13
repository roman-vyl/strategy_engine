"""Mean of a base-bar market field over a leg of the current touch of an EMA
stack episode (OpenSpec `v1-volume-ratio-v1`, `v2-force-ratio-v1`): the impulse
`[S*, P]` or the pullback `[P + 1, t]`, both ends inclusive. Prefix sums,
O(bars)."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

FORCE_FIELDS = ("force_with", "force_against")
LEG_MEAN_FIELDS = ("volume", *FORCE_FIELDS)


def force_series(close: np.ndarray, volume: np.ndarray, field: str, side: str) -> np.ndarray:
    """The side-signed candle force `(close[u] - close[u-1]) * volume[u]`
    (0 on the first bar of the window); positive is with the trade for
    `force_with` and against it for `force_against`. Not mirrored per side:
    only the sign `g` flips (`v2-force-ratio-v1`, D2)."""

    sign = 1.0 if side == "long" else -1.0
    if field == "force_against":
        sign = -sign
    out = np.empty(len(close))
    if len(close):
        out[0] = 0.0
        out[1:] = np.diff(close) * volume[1:]
    out *= sign
    out.flags.writeable = False
    return out


def leg_bar_counts(episode: SideEpisode, size: int, leg: str) -> np.ndarray:
    """Bars of the leg on every bar of the series (NaN where the touch has no
    valid wave or the leg is empty); with the mean it gives the leg sum."""

    valid, origin, peak = touch_points(episode, size)
    if leg == "impulse":
        count = peak - origin + 1
    else:
        count = np.arange(size) - peak
        valid = valid & (count >= 1)
    out = np.where(valid, count, math.nan).astype(np.float64)
    out.flags.writeable = False
    return out


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
