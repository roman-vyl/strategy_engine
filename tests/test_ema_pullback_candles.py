"""B1 candle operand (OpenSpec `b1-candle-ratio-v1`): parsing, and the largest
normalised body of a leg against a loop written like the research reference
(per-candle Wilder ATR; a forming candle takes the ATR of the previous one)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.implementations.atr import atr_wilder
from strategy_engine.strategies.ema_pullback.candles import candle_values

BASE_MS = 300_000
PERIOD = 4  # short, so that the fixtures leave many candles with an ATR


def _atr_spec(timeframe: str = "15m") -> dict[str, Any]:
    return {"kind": "atr_wilder", "timeframe": timeframe, "params": {"period": 14}}


def _candle(**fields: Any) -> dict[str, Any]:
    return {
        "episode": "trend",
        "leg": "pullback",
        "timeframe": "15m",
        "direction": "against",
        "atr": _atr_spec(),
        **fields,
    }


# -- parsing -----------------------------------------------------------------------


def test_candle_parses_and_plans_its_atr() -> None:
    predicate = _parse({"candle": _candle()})
    candle = predicate.long.operand.candle
    assert (candle.leg, candle.timeframe, candle.direction) == ("pullback", "15m", "against")
    assert [f.output_id for f in predicate.features()] == ["atr_wilder_close_15m_14"]
    assert _parse({"candle": _candle(atr=None)}).long.operand.candle.atr is None
    ratio = _parse(
        {
            "ratio": {
                "left": {"candle": _candle()},
                "right": {"candle": _candle(leg="impulse", direction="with")},
            }
        }
    )
    assert ratio.long.operand.ratio is not None


@pytest.mark.parametrize(
    "fields",
    [
        {"leg": "peak"},
        {"direction": "up"},
        {"timeframe": "base"},
        {"timeframe": "7x"},
        {"atr": {"kind": "atr", "timeframe": "15m", "params": {"period": 14}}},
        {"atr": _atr_spec("1h")},
        {"episode": "other"},
        {"extra": 1},
    ],
)
def test_invalid_candle_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"candle": _candle(**fields)})


@pytest.mark.parametrize("missing", ["episode", "leg", "timeframe", "direction"])
def test_required_fields(missing: str) -> None:
    payload = _candle()
    del payload[missing]
    with pytest.raises(InvalidRequestError):
        _parse({"candle": payload})


# -- values against the research loop --------------------------------------------------


def _bars(seed: int) -> tuple[Any, np.ndarray, tuple[np.ndarray, ...], np.ndarray]:
    episode, size, (high, low, close) = _episode_bars(seed)
    open_ = np.concatenate(([close[0]], close[:-1]))
    time_ms = (np.arange(size) + 7) * BASE_MS  # an arbitrary offset onto the grid
    return episode, time_ms, (open_, high, low, close), np.arange(size)


def _candles(
    time_ms: np.ndarray, bars: tuple[np.ndarray, ...], timeframe_ms: int, period: int = PERIOD
) -> tuple[pd.DataFrame, np.ndarray]:
    open_, high, low, close = bars
    frame = pd.DataFrame(
        {"t": time_ms // timeframe_ms, "o": open_, "h": high, "l": low, "c": close}
    )
    grouped = frame.groupby("t", sort=True)
    candles = pd.DataFrame(
        {"o": grouped.o.first(), "h": grouped.h.max(), "l": grouped.l.min(), "c": grouped.c.last()}
    )
    candles["atr"] = atr_wilder(candles.h, candles.l, candles.c, period=period).to_numpy()
    return candles, frame.t.to_numpy()


def _feature(
    candles: pd.DataFrame, time_ms: np.ndarray, timeframe_ms: int, base_ms: int
) -> np.ndarray:
    """The aligned feature: the ATR of the last candle complete by the open of the bar."""

    if timeframe_ms == base_ms:
        return np.asarray(candles["atr"].to_numpy())
    out = np.full(len(time_ms), math.nan)
    for i, moment in enumerate(time_ms):
        done = candles[(candles.index + 1) * timeframe_ms <= moment]
        if len(done):
            out[i] = done["atr"].iloc[-1]
    return out


def _reference(
    episode: Any,
    time_ms: np.ndarray,
    bars: tuple[np.ndarray, ...],
    timeframe_ms: int,
    leg: str,
    direction: str,
    side: str,
    normalise: bool,
    period: int = PERIOD,
) -> np.ndarray:
    open_, _, _, close = bars
    candles, bucket = _candles(time_ms, bars, timeframe_ms, period)
    position = {key: i for i, key in enumerate(candles.index)}
    sign = 1.0 if (direction == "with") == (side == "long") else -1.0
    out = np.full(len(time_ms), math.nan)
    for t in range(len(time_ms)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if peak > t:
            continue
        a, e = (origin, peak) if leg == "impulse" else (peak + 1, t)
        if a > e:
            continue
        best = 0.0
        for key in dict.fromkeys(bucket[a : e + 1]):
            members = [i for i in range(a, e + 1) if bucket[i] == key]
            body = max(sign * (close[members[-1]] - open_[members[0]]), 0.0)
            closed = time_ms[members[-1]] + BASE_MS >= (key + 1) * timeframe_ms
            k = position[key]
            if not normalise:
                best = max(best, body)
                continue
            atr = (
                candles["atr"].iloc[k]
                if closed
                else (candles["atr"].iloc[k - 1] if k else math.nan)
            )
            if math.isfinite(atr) and atr > 0:
                best = max(best, body / atr)
        out[t] = best
    return out


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("timeframe_ms", [BASE_MS, 3 * BASE_MS, 12 * BASE_MS])
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
@pytest.mark.parametrize("direction", ["with", "against"])
@pytest.mark.parametrize("side", ["long", "short"])
def test_matches_the_research_loop(
    seed: int, timeframe_ms: int, leg: str, direction: str, side: str
) -> None:
    episode, time_ms, bars, _ = _bars(seed)
    open_, high, low, close = bars
    candles, _ = _candles(time_ms, bars, timeframe_ms)
    atr = _feature(candles, time_ms, timeframe_ms, BASE_MS)
    for normalise in (True, False):
        got = candle_values(
            episode,
            time_ms=time_ms,
            open_=open_,
            high=high,
            low=low,
            close=close,
            timeframe_ms=timeframe_ms,
            base_ms=BASE_MS,
            leg=leg,
            direction=direction,
            side=side,
            atr=atr if normalise else None,
            atr_period=PERIOD if normalise else None,
        )
        expected = _reference(episode, time_ms, bars, timeframe_ms, leg, direction, side, normalise)
        np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-12, equal_nan=True)
        assert np.isfinite(expected).sum() > 20
        if side == "long" and (leg, direction) in {("impulse", "with"), ("pullback", "against")}:
            assert (expected > 0).any()


def test_pullback_needs_a_bar_after_the_peak_and_only_bars_up_to_t_are_read() -> None:
    episode, time_ms, bars, _ = _bars(1)
    open_, high, low, close = bars
    candles, _ = _candles(time_ms, bars, 3 * BASE_MS)
    atr = _feature(candles, time_ms, 3 * BASE_MS, BASE_MS)

    def run(close_array: np.ndarray, open_array: np.ndarray) -> np.ndarray:
        return candle_values(
            episode,
            time_ms=time_ms,
            open_=open_array,
            high=high,
            low=low,
            close=close_array,
            timeframe_ms=3 * BASE_MS,
            base_ms=BASE_MS,
            leg="pullback",
            direction="against",
            side="long",
            atr=atr,
            atr_period=PERIOD,
        )

    full = run(close, open_)
    for t in range(len(close)):
        legs = _legs(episode, t)
        if np.isfinite(full[t]):
            assert legs is not None and legs[1] < t  # no pullback bar, no value
    assert np.isfinite(full).any()
    cut = len(close) // 2
    close2, open2 = close.copy(), open_.copy()
    close2[cut + 1 :] += 40.0
    open2[cut + 1 :] -= 40.0
    np.testing.assert_array_equal(run(close2, open2)[: cut + 1], full[: cut + 1])


def _truncated_episode(seed: int, count: int) -> Any:
    from test_ema_pullback_predicates_a2 import _params_for

    from strategy_engine.strategies.ema_pullback.stack_episode import project_side

    _, size, (high, low, close) = _episode_bars(seed)
    fast = np.array([99.0] + [101.0] * (size - 1))
    return project_side(
        high[:count],
        low[:count],
        close[:count],
        fast[:count],
        np.full(count, 100.0),
        np.full(count, 99.0),
        _params_for(3),
        "long",
    )


@pytest.mark.parametrize("timeframe_ms", [BASE_MS, 3 * BASE_MS, 12 * BASE_MS])
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
def test_a_series_cut_at_t_gives_the_value_of_the_full_series(timeframe_ms: int, leg: str) -> None:
    """Live, the series ends at the evaluated bar: a candle still forming there is
    not closed, whatever the cut (the full series is the backtest)."""

    seed = 2
    episode, time_ms, bars, _ = _bars(seed)
    open_, high, low, close = bars
    candles, _ = _candles(time_ms, bars, timeframe_ms)
    full_atr = _feature(candles, time_ms, timeframe_ms, BASE_MS)

    def run(count: int, ep: Any, atr: np.ndarray) -> np.ndarray:
        return candle_values(
            ep,
            time_ms=time_ms[:count],
            open_=open_[:count],
            high=high[:count],
            low=low[:count],
            close=close[:count],
            timeframe_ms=timeframe_ms,
            base_ms=BASE_MS,
            leg=leg,
            direction="against" if leg == "pullback" else "with",
            side="long",
            atr=atr[:count],
            atr_period=PERIOD,
        )

    full = run(len(time_ms), episode, full_atr)
    checked = 0
    for t in range(40, len(time_ms)):
        if not np.isfinite(full[t]):
            continue
        cut_candles, _ = _candles(time_ms[: t + 1], tuple(b[: t + 1] for b in bars), timeframe_ms)
        cut_atr = _feature(cut_candles, time_ms[: t + 1], timeframe_ms, BASE_MS)
        got = run(t + 1, _truncated_episode(seed, t + 1), cut_atr)[t]
        np.testing.assert_allclose(got, full[t], rtol=1e-9, atol=1e-12)
        checked += 1
    assert checked > 50
