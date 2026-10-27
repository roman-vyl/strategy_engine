"""Percent change of a base-bar field between the two ends of a leg of an
EMA stack episode (OpenSpec `o1-leg-change-v1`): `100 * (x[end] / x[begin] - 1)`
over the impulse `[S*, P]` or the pullback `[P, t]` of the current touch, or
the impulse `[S*0, P0]` of the previous touch. O1 is the impulse change of
the open interest."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.indicators.market_arrays import OPEN_INTEREST_FIELD
from strategy_engine.strategies.ema_pullback.anchor_follow import _touch_rows
from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

LEG_CHANGE_FIELDS = ("close", OPEN_INTEREST_FIELD)


def leg_change_values(
    episode: SideEpisode, series: np.ndarray, leg: str, touch: str = "current"
) -> np.ndarray:
    """The leg change on every bar as a read-only float64 array; missing where
    the touch has no valid wave (or no previous touch), an end value is not
    finite or the begin value is not positive. Only the two end bars are
    read, both at or before the evaluated bar."""

    size = len(episode.state["touch_number"])
    out = np.full(size, math.nan)
    valid, origin, peak = touch_points(episode, size)
    if not valid.any():
        out.flags.writeable = False
        return out
    if touch == "previous":
        touches = episode.touches
        rows = _touch_rows(episode, size)
        valid = valid & (episode.state["touch_number"] >= 2)
        previous = np.where(valid, rows - 1, 0)
        begin_raw = touches["origin_bar"][previous]
        end_raw = touches["peak_bar"][previous]
        with np.errstate(invalid="ignore"):
            valid = valid & np.isfinite(begin_raw) & np.isfinite(end_raw) & (begin_raw <= end_raw)
        begin = np.where(valid, begin_raw, 0).astype(np.int64)
        end = np.where(valid, end_raw, 0).astype(np.int64)
    elif leg == "impulse":
        begin, end = origin, peak
    else:
        begin, end = peak, np.arange(size)
    values = np.asarray(series, dtype=np.float64)
    first = values[np.where(valid, begin, 0)]
    last = values[np.where(valid, end, 0)]
    with np.errstate(invalid="ignore"):
        ok = valid & np.isfinite(first) & np.isfinite(last) & (first > 0)
    out[ok] = 100.0 * (last[ok] / first[ok] - 1.0)
    out.flags.writeable = False
    return out
