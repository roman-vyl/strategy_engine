"""How much of the impulse the pullback gave back (OpenSpec
`c3-pullback-depth-share-v1`): `g * (peak_price - ext[t]) / |peak_price -
origin_price|` for the current touch of an EMA stack episode, `ext[t]` the
lowest low (long) or highest high (short) of the bars `[P, t]`, `g` +1 on the
long side and -1 on the short side. With `touch: previous`
(`c3-previous-depth-ratio-v1`) the same share for the previous touch row of
the episode, its pullback measured over `[P0, S*]`."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.anchor_follow import _touch_rows
from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode


def pullback_depth_values(
    episode: SideEpisode, low: np.ndarray, high: np.ndarray, touch: str = "current"
) -> np.ndarray:
    """The C3.1 value (`touch` current) or the previous depth (`previous`) on
    every bar as a read-only float64 array; missing where the touch has no
    valid wave, the impulse height is 0 or a price of the measured range is
    not finite. Nothing after the evaluated bar is read."""

    size = len(episode.state["touch_number"])
    out = np.full(size, math.nan)
    valid, _, peak = touch_points(episode, size)
    if len(episode.touches["peak_price"]) == 0 or not valid.any():
        out.flags.writeable = False
        return out
    long = episode.side == "long"
    g = 1.0 if long else -1.0
    rows = _touch_rows(episode, size)
    if touch == "previous":
        _previous_depth(episode, low if long else high, valid, rows, g, out)
        out.flags.writeable = False
        return out
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


def _previous_depth(
    episode: SideEpisode,
    prices: np.ndarray,
    valid: np.ndarray,
    rows: np.ndarray,
    g: float,
    out: np.ndarray,
) -> None:
    """Fill `out` with the depth share of the previous pullback `[P0, S*]` on
    bars whose current touch is valid and not the first of its episode; one
    value per touch row. `S* <= P <= t`, so nothing after `t` is read."""

    touches = episode.touches
    has_previous = valid & (episode.state["touch_number"] >= 2)
    cache: dict[int, float] = {}
    for t in np.flatnonzero(has_previous):
        row = int(rows[t])
        value = cache.get(row)
        if value is None:
            value = math.nan
            p0, s = int(touches["peak_bar"][row - 1]), int(touches["origin_bar"][row])
            peak0 = float(touches["peak_price"][row - 1])
            height = abs(peak0 - float(touches["origin_price"][row - 1]))
            if s > p0 and height > 0.0:
                window = np.asarray(prices[p0 : s + 1], dtype=np.float64)
                ext = float(window.min() if g > 0 else window.max())
                if math.isfinite(ext):
                    value = g * (peak0 - ext) / height
            cache[row] = value
        out[t] = value
