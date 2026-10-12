"""Candles of a leg of the current touch of an EMA stack episode (OpenSpec
`b1-candle-ratio-v1`): the largest body, with or against the trade, over the
timeframe candles that the leg's base bars build, each body divided by the
ATR of its own candle.

Everything is vectorised over bars: base bars are bucketed by their open time
on the timeframe grid, every bucket has one open, close, high and low, and
the candles of a leg are its clipped first and last bucket plus the full
buckets between them, whose normalised bodies are read through a sparse table.
"""

from __future__ import annotations

import math

import numpy as np

from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode
from strategy_engine.strategies.ema_pullback.window_extreme import window_extreme

CANDLE_ATR_FIELD = "atr"  # the wire name of the normalising feature
CANDLE_ATR_KIND = "atr_wilder"  # the only ATR a candle accepts: Wilder, as the reference


def touch_points(episode: SideEpisode, size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(valid, origin, peak)` of the current touch on every bar; both bars
    are indices, only meaningful where `valid`."""

    state = episode.state
    number = state["touch_number"]
    live = np.isfinite(number)
    count = np.where(live, number, 0.0)
    valid = live & (count >= 1)
    episode_id = np.where(live, state["episode_id"], 0.0).astype(np.int64)
    first = episode.first_row[np.clip(episode_id, 0, len(episode.first_row) - 1)]
    rows = np.where(valid, first + count.astype(np.int64) - 1, 0)
    origin = np.where(valid, episode.touches["origin_bar"][rows], math.nan)
    peak = np.where(valid, episode.touches["peak_bar"][rows], math.nan)
    current = np.arange(size, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        valid = (
            valid & np.isfinite(origin) & np.isfinite(peak) & (origin <= peak) & (peak <= current)
        )
    return (
        valid,
        np.where(valid, origin, 0).astype(np.int64),
        np.where(valid, peak, 0).astype(np.int64),
    )


def _normalised(body: np.ndarray, atr: np.ndarray | None) -> np.ndarray:
    """`max(body, 0) / atr`; a candle without a positive ATR counts 0 (it is
    skipped), without an ATR series the body stays in price units."""

    positive = np.maximum(body, 0.0)
    if atr is None:
        return np.asarray(np.where(np.isfinite(positive), positive, 0.0))
    usable = np.isfinite(atr) & (atr > 0) & np.isfinite(positive)
    out = np.zeros(len(body))
    np.divide(positive, atr, out=out, where=usable)
    return out


def candle_values(
    episode: SideEpisode,
    *,
    time_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    timeframe_ms: int,
    base_ms: int,
    leg: str,
    direction: str,
    side: str,
    atr: np.ndarray | None,
    atr_period: int | None,
) -> np.ndarray:
    """The B1 candle operand on every bar as a read-only float64 array."""

    size = len(time_ms)
    out = np.full(size, math.nan)
    out.flags.writeable = False
    if size == 0:
        return out
    bucket = time_ms // timeframe_ms
    starts = np.concatenate(([True], bucket[1:] != bucket[:-1]))
    ordinal = np.cumsum(starts) - 1
    first_bar = np.flatnonzero(starts)
    last_bar = np.concatenate((first_bar[1:] - 1, [size - 1]))
    bucket_open, bucket_close = open_[first_bar], close[last_bar]
    sign = 1.0 if (direction == "with") == (side == "long") else -1.0

    if atr is None:
        prev_atr = own_atr = None
    else:
        if timeframe_ms == base_ms:
            own_atr = atr[first_bar]
            prev_atr = np.where(first_bar > 0, atr[np.maximum(first_bar - 1, 0)], math.nan)
        else:
            assert atr_period is not None
            prev_atr = atr[first_bar]
            bucket_high = np.maximum.reduceat(high, first_bar)
            bucket_low = np.minimum.reduceat(low, first_bar)
            previous_close = np.concatenate(([math.nan], bucket_close[:-1]))
            true_range = np.maximum.reduce(
                [
                    bucket_high - bucket_low,
                    np.abs(bucket_high - previous_close),
                    np.abs(bucket_low - previous_close),
                ]
            )
            true_range = np.where(np.isfinite(true_range), true_range, bucket_high - bucket_low)
            starts_at = bucket[first_bar]
            adjacent = np.concatenate(([False], starts_at[1:] - starts_at[:-1] == 1))
            recurred = np.where(
                adjacent, (prev_atr * (atr_period - 1) + true_range) / atr_period, math.nan
            )
            # The ATR of a complete candle is the aligned value at the open of the next
            # one (it covers the seed candle); the last candle of the series, which has
            # no next one yet, continues the previous candle's ATR by the recursion.
            following = np.concatenate((prev_atr[1:], [math.nan]))
            next_adjacent = np.concatenate((adjacent[1:], [False]))
            own_atr = np.where(next_adjacent, following, recurred)

    def pick(values: np.ndarray | None, index: np.ndarray) -> np.ndarray | None:
        return None if values is None else values[index]

    full = _normalised(sign * (bucket_close - bucket_open), own_atr)

    valid, origin, peak = touch_points(episode, size)
    current = np.arange(size)
    if leg == "impulse":
        begin, end = origin, peak
    else:
        begin, end = peak + 1, current
        valid = valid & (begin <= end)
    begin = np.where(valid, begin, 0)
    end = np.where(valid, end, 0)
    b_begin, b_end = ordinal[begin], ordinal[end]
    # Closed by the time grid, not by the end of the series: live, the series ends at `t`.
    end_closes_bucket = time_ms[end] + base_ms >= (bucket[end] + 1) * timeframe_ms

    # one candle: begin and end in the same bucket
    single_atr = (
        None
        if own_atr is None or prev_atr is None
        else np.where(end_closes_bucket, own_atr[b_end], prev_atr[b_end])
    )
    single = _normalised(sign * (close[end] - open_[begin]), single_atr)
    # several candles: clipped first bucket, clipped last bucket, full buckets between
    first = _normalised(sign * (bucket_close[b_begin] - open_[begin]), pick(own_atr, b_begin))
    last = _normalised(sign * (close[end] - bucket_open[b_end]), single_atr)
    result = np.where(b_begin == b_end, single, np.maximum(first, last))
    between = valid & (b_end - b_begin >= 2)
    rows = np.flatnonzero(between)
    if len(rows):
        result[rows] = np.maximum(
            result[rows], window_extreme(full, b_begin[rows] + 1, b_end[rows] - 1, True)
        )
    out = np.where(valid, result, math.nan)
    out.flags.writeable = False
    return out
