"""C3.1 pullback depth operand (OpenSpec `c3-pullback-depth-share-v1`): parsing, the
value against a loop written like the research reference (`altvals.py` `c31`), the
mirrored short, missing cases and no look-ahead."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.pullback_depth import pullback_depth_values


def _operand(**fields: Any) -> dict[str, Any]:
    return {"pullback_depth": {"episode": "trend", **fields}}


def reference(episode: Any, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """`altvals.py`: `ext = L[P:b+1].min()` (long) or `H[P:b+1].max()` (short),
    `c31 = g * (Pp - ext) / |Pp - Sp|` when the height is above 0."""

    g = 1.0 if episode.side == "long" else -1.0
    out = np.full(len(low), math.nan)
    for t in range(len(low)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])])
        row += int(episode.state["touch_number"][t]) - 1
        pp = float(episode.touches["peak_price"][row])
        sp = float(episode.touches["origin_price"][row])
        ext = low[peak : t + 1].min() if g > 0 else high[peak : t + 1].max()
        height = abs(pp - sp)
        if height > 0 and math.isfinite(ext):
            out[t] = g * (pp - ext) / height
    return out


def test_pullback_depth_parses_as_a_range_and_ratio_operand() -> None:
    assert _parse(_operand()).long.operand.pullback_depth.episode == "trend"
    ratio = {"ratio": {"left": _operand(), "right": _operand()}}
    assert _parse(ratio).long.operand.ratio.right.pullback_depth.episode == "trend"


@pytest.mark.parametrize("fields", [{"episode": "other"}, {"episode": ""}, {"extra": 1}])
def test_malformed_pullback_depth_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"pullback_depth": {**_operand()["pullback_depth"], **fields}})


def test_episode_is_required() -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"pullback_depth": {}})


def test_pullback_depth_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
def test_pullback_depth_matches_the_loop(seed: int, side: str) -> None:
    episode, _, (high, low, _) = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    got = pullback_depth_values(episode, low, high)
    expected = reference(episode, low, high)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any()
    assert not got.flags.writeable


def test_non_finite_price_makes_the_rest_of_the_touch_missing() -> None:
    episode, size, (high, low, _) = _episode_bars(4)
    base = pullback_depth_values(episode, low, high)
    t = int(np.flatnonzero(np.isfinite(base))[len(np.flatnonzero(np.isfinite(base))) // 2])
    bad = low.copy()
    bad[t] = math.nan
    got = pullback_depth_values(episode, bad, high)
    expected = reference(episode, bad, high)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0, equal_nan=True)
    assert math.isnan(got[t]) and np.isfinite(got[:t]).sum() == np.isfinite(base[:t]).sum()


def test_zero_impulse_height_is_missing() -> None:
    episode, _, (high, low, _) = _episode_bars(5)
    touches = dict(episode.touches)
    touches["origin_price"] = np.array(touches["peak_price"], dtype=float)
    flat = dataclasses.replace(episode, touches=touches)
    assert np.isnan(pullback_depth_values(flat, low, high)).all()


def test_no_look_ahead() -> None:
    episode, size, (high, low, _) = _episode_bars(2)
    full = pullback_depth_values(episode, low, high)
    for cut in (size // 3, size // 2, size - 5):
        changed_low, changed_high = low.copy(), high.copy()
        changed_low[cut + 1 :] = 0.0
        changed_high[cut + 1 :] = 1e9
        got = pullback_depth_values(episode, changed_low, changed_high)
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


def test_spec_examples() -> None:
    assert (110.0 - 103.0) / abs(110.0 - 100.0) == pytest.approx(0.7)
    assert -1.0 * (100.0 - 104.0) / abs(100.0 - 110.0) == pytest.approx(0.4)


# -- touch previous (OpenSpec `c3-previous-depth-ratio-v1`) ------------------------


def previous_reference(episode: Any, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """`altvals.py` C3.2: `ext0 = L[P0:S+1].min()` (long) or `H[P0:S+1].max()`,
    `v0 = g * (Pp0 - ext0) / |Pp0 - Sp0|` when `S > P0` and the height is above 0."""

    g = 1.0 if episode.side == "long" else -1.0
    out = np.full(len(low), math.nan)
    for t in range(len(low)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        number = int(episode.state["touch_number"][t])
        if not (origin <= peak <= t) or number < 2:
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])]) + number - 1
        p0 = int(episode.touches["peak_bar"][row - 1])
        pp0 = float(episode.touches["peak_price"][row - 1])
        sp0 = float(episode.touches["origin_price"][row - 1])
        if origin <= p0 or abs(pp0 - sp0) == 0:
            continue
        ext0 = low[p0 : origin + 1].min() if g > 0 else high[p0 : origin + 1].max()
        if math.isfinite(ext0):
            out[t] = g * (pp0 - ext0) / abs(pp0 - sp0)
    return out


def test_touch_parses_and_defaults_to_current() -> None:
    assert _parse(_operand()).long.operand.pullback_depth.touch == "current"
    assert _parse(_operand(touch="previous")).long.operand.pullback_depth.touch == "previous"
    with pytest.raises(InvalidRequestError):
        _parse(_operand(touch="next"))


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
def test_previous_depth_matches_the_loop(seed: int, side: str) -> None:
    episode, _, (high, low, _) = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    got = pullback_depth_values(episode, low, high, "previous")
    expected = previous_reference(episode, low, high)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and not got.flags.writeable
    first = np.asarray(episode.state["touch_number"]) == 1
    assert first.any() and np.isnan(got[first]).all()


def test_previous_depth_zero_height_is_missing() -> None:
    episode, _, (high, low, _) = _episode_bars(5)
    touches = dict(episode.touches)
    touches["origin_price"] = np.array(touches["peak_price"], dtype=float)
    flat = dataclasses.replace(episode, touches=touches)
    assert np.isnan(pullback_depth_values(flat, low, high, "previous")).all()


def test_previous_depth_no_look_ahead() -> None:
    episode, size, (high, low, _) = _episode_bars(2)
    full = pullback_depth_values(episode, low, high, "previous")
    for cut in (size // 3, size // 2, size - 5):
        changed_low, changed_high = low.copy(), high.copy()
        changed_low[cut + 1 :] = 0.0
        changed_high[cut + 1 :] = 1e9
        got = pullback_depth_values(episode, changed_low, changed_high, "previous")
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])
