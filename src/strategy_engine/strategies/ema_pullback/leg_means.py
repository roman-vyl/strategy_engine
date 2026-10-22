"""Mean or sum of a base-bar market field over a leg of the current touch of
an EMA stack episode (OpenSpec `v1-volume-ratio-v1`, `v2-force-ratio-v1`,
`v1-volume-sum-ratio-v1`): the impulse `[S*, P]` or the pullback `[P + 1, t]`,
both ends inclusive. Prefix sums, O(bars)."""

from __future__ import annotations

import bisect
import math

import numpy as np

from strategy_engine.strategies.ema_pullback.candles import touch_points
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode

FORCE_FIELDS = ("force_with", "force_against")
LEG_MEAN_FIELDS = ("volume", *FORCE_FIELDS)
OWN_COLOR_VOLUME = "own_color_volume"
LEG_SUM_FIELDS = ("volume", OWN_COLOR_VOLUME)


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


def own_color_volume_series(
    open_: np.ndarray, close: np.ndarray, volume: np.ndarray, side: str, leg: str
) -> np.ndarray:
    """Volume of the bars whose candle has the leg's own colour, 0 elsewhere:
    with the trade on the impulse, against it on the pullback; a doji never
    counts. Non-finite where open, close or volume is not finite
    (`v1-own-color-volume-ratio-v1`, D1)."""

    body = (close - open_) * (1.0 if side == "long" else -1.0)
    own = body > 0 if leg == "impulse" else body < 0
    with np.errstate(invalid="ignore"):
        out = np.where(own, volume, 0.0)
    finite = np.isfinite(open_) & np.isfinite(close) & np.isfinite(volume)
    out = np.where(finite, out, math.nan)
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


def _leg_totals(
    episode: SideEpisode, series: np.ndarray, leg: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per bar: whether the leg is valid, the sum of `series` over it and its
    bar count. A leg is invalid where the touch has no valid wave, the leg is
    empty or a bar of it is not finite."""

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
    return valid, total[end + 1] - total[begin], end - begin + 1


def leg_mean_values(episode: SideEpisode, series: np.ndarray, leg: str) -> np.ndarray:
    """The leg mean on every bar as a read-only float64 array; missing where
    the touch has no valid wave, the leg is empty or a bar of it is not finite."""

    valid, total, count = _leg_totals(episode, series, leg)
    out = np.where(valid, total / count, math.nan)
    out.flags.writeable = False
    return out


def leg_sum_values(episode: SideEpisode, series: np.ndarray, leg: str) -> np.ndarray:
    """The leg sum on every bar as a read-only float64 array, with the legs and
    missing rules of the leg mean (`v1-volume-sum-ratio-v1`, D1)."""

    valid, total, _ = _leg_totals(episode, series, leg)
    out = np.where(valid, total, math.nan)
    out.flags.writeable = False
    return out


LEG_TOP_MEAN_FIELDS = ("volume",)


def _top_mean(ordered: list[float], share: float) -> float:
    k = max(1, math.ceil(share * len(ordered)))
    return math.fsum(ordered[-k:]) / k


def leg_top_mean_values(
    episode: SideEpisode, series: np.ndarray, leg: str, share: float
) -> np.ndarray:
    """Mean of the `k = max(1, ceil(share * L))` largest values of `series`
    over the leg on every bar (`v1-top-volume-ratio-v1`, D1, D2), with the legs
    and missing rules of the leg sum. The impulse is sorted once per touch;
    the pullback window is kept sorted while `t` grows within a touch."""

    size = len(series)
    valid, origin, peak = touch_points(episode, size)
    out = np.full(size, math.nan)
    finite = np.isfinite(series)
    bad = np.zeros(size + 1, dtype=np.int64)
    np.cumsum(~finite, out=bad[1:])
    impulse_cache: dict[tuple[int, int], float] = {}
    window: list[float] = []
    window_begin, window_end = -1, -1
    for t in np.flatnonzero(valid):
        if leg == "impulse":
            begin, end = int(origin[t]), int(peak[t])
        else:
            begin, end = int(peak[t]) + 1, int(t)
            if begin > end:
                continue
        if bad[end + 1] - bad[begin]:
            continue
        if leg == "impulse":
            key = (begin, end)
            if key not in impulse_cache:
                impulse_cache[key] = _top_mean(sorted(series[begin : end + 1].tolist()), share)
            out[t] = impulse_cache[key]
            continue
        if begin == window_begin and end == window_end + 1:
            bisect.insort(window, float(series[end]))
        else:
            window = sorted(series[begin : end + 1].tolist())
        window_begin, window_end = begin, end
        out[t] = _top_mean(window, share)
    out.flags.writeable = False
    return out
