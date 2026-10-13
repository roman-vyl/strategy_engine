"""Who closed the gap to the anchor, price or the EMA (OpenSpec
`c5-anchor-follow-v1`): `g * (EMA[t] - EMA[P]) / (g * (peak_price - EMA[P]))`
for the current touch of an EMA stack episode, `g` +1 on the long side and -1
on the short side. The anchor series is the one the episode was built from."""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode


def _touch_rows(episode: SideEpisode, size: int) -> np.ndarray:
    """Touch-table row of the current touch on every bar (0 where none)."""

    state = episode.state
    number = state["touch_number"]
    live = np.isfinite(number)
    count = np.where(live, number, 0.0)
    episode_id = np.where(live, state["episode_id"], 0.0).astype(np.int64)
    first = episode.first_row[np.clip(episode_id, 0, len(episode.first_row) - 1)]
    rows = np.where(live & (count >= 1), first + count.astype(np.int64) - 1, 0)
    return np.clip(rows, 0, max(len(episode.touches["peak_bar"]) - 1, 0))


def anchor_follow_parts(
    episode: SideEpisode, size: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(peak_price, gap, move)` on every bar, NaN where the touch has no
    valid wave. Prices are in the side's own units, so `g` mirrors the short
    side; nothing after the evaluated bar is read."""

    anchor = episode.anchor
    if anchor is None:
        raise InvalidRequestError("episode carries no anchor series", side=episode.side)
    valid, _, peak = touch_points(episode, size)
    if len(episode.touches["peak_bar"]) == 0:
        valid = np.zeros(size, dtype=bool)
    rows = _touch_rows(episode, size)
    g = 1.0 if episode.side == "long" else -1.0
    peak_price = np.where(valid, episode.touches["peak_price"][rows], math.nan)
    ema_p = anchor[peak]
    ema_t = anchor
    with np.errstate(invalid="ignore"):
        gap = np.where(valid, g * (peak_price - ema_p), math.nan)
        move = np.where(valid, g * (ema_t - ema_p), math.nan)
    return peak_price, gap, move


def anchor_follow_values(episode: SideEpisode) -> np.ndarray:
    """The C5 value on every bar as a read-only float64 array; missing where
    the touch has no valid wave, the gap is not greater than 0 or an input is
    not finite."""

    size = len(episode.state["touch_number"])
    _, gap, move = anchor_follow_parts(episode, size)
    ok = np.isfinite(gap) & np.isfinite(move) & (gap > 0.0)
    out = np.where(ok, move / np.where(ok, gap, 1.0), math.nan)
    out.flags.writeable = False
    return out
