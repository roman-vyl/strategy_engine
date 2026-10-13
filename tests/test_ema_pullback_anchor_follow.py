"""C5 anchor follow operand (OpenSpec `c5-anchor-follow-v1`): parsing, the value
against a loop written like the research reference (`c5_engine_ref.py`), the
mirrored short, missing cases, thresholds and no look-ahead."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.anchor_follow import (
    anchor_follow_parts,
    anchor_follow_values,
)
from strategy_engine.strategies.ema_pullback.predicates import _range_mask


def _operand(**fields: Any) -> dict[str, Any]:
    return {"anchor_follow": {"episode": "trend", **fields}}


def _with_anchor(seed: int, side: str = "long", scale: float = 0.05) -> tuple[Any, int]:
    """A fixture episode whose anchor series is replaced by a moving one (the
    operand reads `episode.anchor`; the fixture's own anchor is flat)."""

    episode, size = _episode(seed)
    rng = np.random.default_rng(seed + 11)
    base = 100.0 if side == "long" else 150.0  # a short needs the anchor above the low
    anchor = base + np.cumsum(rng.normal(0.0, scale, size))
    return dataclasses.replace(episode, side=side, anchor=anchor), size


def _reference(episode: Any, size: int) -> np.ndarray:
    g = 1.0 if episode.side == "long" else -1.0
    out = np.full(size, math.nan)
    for t in range(size):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])])
        row += int(episode.state["touch_number"][t]) - 1
        peak_price = float(episode.touches["peak_price"][row])
        gap = g * (peak_price - episode.anchor[peak])
        move = g * (episode.anchor[t] - episode.anchor[peak])
        if gap > 0:
            out[t] = move / gap
    return out


def test_anchor_follow_parses_as_a_range_ratio_and_compare_operand() -> None:
    operand = _parse(_operand()).long.operand.anchor_follow
    assert operand.episode == "trend"
    ratio = {"ratio": {"left": _operand(), "right": {"const": 2.0}}}
    assert _parse(ratio).long.operand.ratio.left.anchor_follow.episode == "trend"


@pytest.mark.parametrize("fields", [{"episode": "other"}, {"episode": ""}, {"extra": 1}])
def test_malformed_anchor_follow_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"anchor_follow": {**_operand()["anchor_follow"], **fields}})


def test_episode_is_required() -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"anchor_follow": {}})


def test_anchor_follow_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("seed", range(6))
def test_value_matches_the_loop(seed: int, side: str) -> None:
    episode, size = _with_anchor(seed, side)
    got = anchor_follow_values(episode)
    expected = _reference(episode, size)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0, equal_nan=True)
    assert np.isfinite(got).any() and np.isnan(got).any()


def test_the_value_is_a_share_of_the_gap_and_can_be_negative() -> None:
    episode, size = _with_anchor(2, scale=0.3)
    values = anchor_follow_values(episode)
    peak_price, gap, move = anchor_follow_parts(episode, size)
    ok = np.isfinite(values)
    np.testing.assert_allclose(values[ok], move[ok] / gap[ok], rtol=1e-12)
    assert (gap[ok] > 0).all()
    assert (values[ok] < 0).any() and (values[ok] > 0).any()


def test_a_gap_that_is_not_positive_makes_the_value_missing() -> None:
    episode, size = _with_anchor(3)
    above = dataclasses.replace(episode, anchor=np.full(size, 1.0e6))
    assert np.isnan(anchor_follow_values(above)).all()
    equal = dataclasses.replace(episode, anchor=episode.anchor.copy())
    row_peaks = equal.touches["peak_price"]
    assert np.isfinite(row_peaks).any()


def test_a_non_finite_anchor_makes_the_value_missing() -> None:
    episode, size = _with_anchor(1)
    base = anchor_follow_values(episode)
    t = int(np.flatnonzero(np.isfinite(base))[5])
    broken = episode.anchor.copy()
    broken[t] = math.nan
    got = anchor_follow_values(dataclasses.replace(episode, anchor=broken))
    assert math.isnan(got[t])


def test_the_short_side_mirrors_the_sign() -> None:
    long_episode, size = _with_anchor(4, "long")
    anchor = long_episode.anchor
    # the same bars as a short: gap = EMA[P] - peak (a low), move = EMA[P] - EMA[t]
    peak_price, gap, move = anchor_follow_parts(long_episode, size)
    short = dataclasses.replace(long_episode, side="short")
    s_price, s_gap, s_move = anchor_follow_parts(short, size)
    np.testing.assert_array_equal(s_price, peak_price)
    np.testing.assert_allclose(s_gap, -gap, equal_nan=True)
    np.testing.assert_allclose(s_move, -move, equal_nan=True)
    assert anchor is short.anchor


def test_only_bars_up_to_the_evaluated_bar_are_read() -> None:
    episode, size = _with_anchor(5)
    full = anchor_follow_values(episode)
    for cut in (size // 3, size // 2):
        altered = episode.anchor.copy()
        altered[cut + 1 :] += 25.0
        got = anchor_follow_values(dataclasses.replace(episode, anchor=altered))
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


def test_an_episode_without_an_anchor_series_fails_closed() -> None:
    episode, size = _episode(1)
    with pytest.raises(InvalidRequestError):
        anchor_follow_values(dataclasses.replace(episode, anchor=None))


def test_project_side_keeps_the_unmirrored_anchor_series() -> None:
    episode, _ = _episode(1)
    assert episode.anchor is not None
    assert (episode.anchor == 100.0).all()


def _band(low: float | None, high: float | None) -> Any:
    cond = _parse(_operand()).long
    return type(cond)(cond.operand, low, high, "exclusive", "pass")


def test_thresholds_are_blocked_inclusively_and_missing_passes() -> None:
    values = np.array([-0.2, 0.017, 0.3, 0.55, 0.9, math.nan])
    assert _range_mask(_band(0.017, 0.55), values).tolist() == [
        False,
        False,
        True,
        False,
        False,
        True,
    ]
    assert _range_mask(_band(None, None), values).all()
    assert _range_mask(_band(None, 0.55), values).tolist() == [True, True, True, False, False, True]
    assert _range_mask(_band(0.017, None), values).tolist() == [
        False,
        False,
        True,
        True,
        True,
        True,
    ]


def _episode_without_touches() -> tuple[Any, int]:
    from strategy_engine.strategies.ema_pullback.stack_episode import (
        EpisodeParams,
        project_side,
    )

    size = 60
    close = np.linspace(100.0, 101.0, size)  # a flat, rising line: the stack never touches
    params = EpisodeParams(3, 5, 8, 4, 4, 100)
    episode = project_side(close + 0.1, close - 0.1, close, close, close, close, params, "long")
    assert len(episode.touches["origin_bar"]) == 0
    return episode, size


def test_an_episode_without_touches_gives_no_value_instead_of_failing() -> None:
    from strategy_engine.strategies.ema_pullback.candles import candle_values, touch_points
    from strategy_engine.strategies.ema_pullback.leg_means import leg_mean_values

    episode, size = _episode_without_touches()
    valid, origin, peak = touch_points(episode, size)
    assert not valid.any() and (origin == 0).all() and (peak == 0).all()
    assert np.isnan(anchor_follow_values(episode)).all()
    volume = np.arange(1.0, size + 1.0)
    for leg in ("impulse", "pullback"):
        assert np.isnan(leg_mean_values(episode, volume, leg)).all()
    close = np.linspace(100.0, 101.0, size)
    time_ms = np.arange(size, dtype=np.int64) * 300_000
    for leg in ("impulse", "pullback"):
        got = candle_values(
            episode,
            time_ms=time_ms,
            open_=close,
            high=close + 0.1,
            low=close - 0.1,
            close=close,
            timeframe_ms=900_000,
            base_ms=300_000,
            leg=leg,
            direction="against",
            side="long",
            atr=None,
            atr_period=None,
        )
        assert np.isnan(got).all()
