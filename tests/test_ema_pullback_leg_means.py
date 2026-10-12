"""V1.3 leg mean operand (OpenSpec `v1-volume-ratio-v1`): parsing, the legs
`[S*, P]` and `[P+1, t]`, missing cases, thresholds and no look-ahead against
a loop written like the research reference (`v1_engine_ref.py`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.leg_means import leg_mean_values
from strategy_engine.strategies.ema_pullback.predicates import _range_mask


def _leg_mean(**fields: Any) -> dict[str, Any]:
    return {"leg_mean": {"episode": "trend", "leg": "pullback", "field": "volume", **fields}}


def test_leg_mean_parses_as_a_range_ratio_and_compare_operand() -> None:
    operand = _parse(_leg_mean()).long.operand.leg_mean
    assert (operand.episode, operand.leg, operand.field) == ("trend", "pullback", "volume")
    ratio = {"ratio": {"left": _leg_mean(), "right": _leg_mean(leg="impulse")}}
    assert _parse(ratio).long.operand.ratio.right.leg_mean.leg == "impulse"


@pytest.mark.parametrize(
    "fields",
    [
        {"leg": "current"},
        {"field": "close"},
        {"episode": "other"},
        {"episode": ""},
        {"extra": 1},
    ],
)
def test_malformed_leg_mean_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_leg_mean(**fields))


@pytest.mark.parametrize("missing", ["episode", "leg", "field"])
def test_required_fields(missing: str) -> None:
    operand = _leg_mean()
    del operand["leg_mean"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_leg_mean_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _leg_mean(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


def _reference(episode: Any, volume: np.ndarray, leg: str) -> np.ndarray:
    out = np.full(len(volume), math.nan)
    for t in range(len(volume)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        begin, end = (origin, peak) if leg == "impulse" else (peak + 1, t)
        if begin > end:
            continue
        window = volume[begin : end + 1]
        if np.isfinite(window).all():
            out[t] = window.sum() / len(window)
    return out


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
def test_leg_mean_matches_the_loop(seed: int, leg: str) -> None:
    episode, size = _episode(seed)
    volume = np.random.default_rng(seed + 40).uniform(1.0, 50.0, size)
    got = leg_mean_values(episode, volume, leg)
    expected = _reference(episode, volume, leg)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0, equal_nan=True)
    assert np.isfinite(got).any() and np.isnan(got).any()


def test_pullback_starts_after_the_peak_and_is_missing_at_the_peak() -> None:
    episode, size = _episode(2)
    volume = np.arange(1.0, size + 1.0)
    pullback = leg_mean_values(episode, volume, "pullback")
    impulse = leg_mean_values(episode, volume, "impulse")
    checked = 0
    for t in range(size):
        legs = _legs(episode, t)
        if legs is None or not legs[0] <= legs[1] <= t:
            continue
        origin, peak, _ = legs
        if t == peak:
            assert math.isnan(pullback[t])
        else:
            assert pullback[t] == pytest.approx(volume[peak + 1 : t + 1].mean())
            checked += 1
        assert impulse[t] == pytest.approx(volume[origin : peak + 1].mean())
    assert checked


def test_a_non_finite_volume_in_a_leg_makes_it_missing() -> None:
    episode, size = _episode(1)
    volume = np.full(size, 10.0)
    base = leg_mean_values(episode, volume, "impulse")
    t = int(np.flatnonzero(np.isfinite(base))[3])
    origin, peak, _ = _legs(episode, t) or (0, 0, 0)
    broken = volume.copy()
    broken[peak] = math.nan
    assert math.isnan(leg_mean_values(episode, broken, "impulse")[t])


@pytest.mark.parametrize("leg", ["impulse", "pullback"])
def test_only_bars_up_to_the_evaluated_bar_are_read(leg: str) -> None:
    episode, size = _episode(4)
    volume = np.random.default_rng(9).uniform(1.0, 50.0, size)
    full = leg_mean_values(episode, volume, leg)
    for cut in (size // 3, size // 2):
        altered = volume.copy()
        altered[cut + 1 :] *= 7.0
        got = leg_mean_values(episode, altered, leg)
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


def _band(low: float | None, high: float | None) -> Any:
    predicate = _parse(_leg_mean())  # parse only to reuse the Range class
    cond = predicate.long
    return type(cond)(cond.operand, low, high, "exclusive", "pass")


def test_thresholds_are_blocked_inclusively_and_missing_passes() -> None:
    values = np.array([0.1, 0.23, 0.5, 4.9, 6.0, math.nan])
    # exclusive band blocks V <= low and V >= high; a missing value passes
    mask = _range_mask(_band(0.23, 4.9), values)
    assert mask.tolist() == [False, False, True, False, False, True]
    assert _range_mask(_band(None, None), values).all()
    assert _range_mask(_band(0.23, None), values).tolist() == [False, False, True, True, True, True]
    assert _range_mask(_band(None, 4.9), values).tolist() == [True, True, True, False, False, True]


def test_zero_impulse_volume_makes_the_ratio_missing() -> None:
    episode, size = _episode(3)
    volume = np.zeros(size)
    impulse = leg_mean_values(episode, volume, "impulse")
    finite = np.isfinite(impulse)
    assert finite.any() and (impulse[finite] == 0).all()
    right = impulse
    left = leg_mean_values(episode, volume + 1.0, "pullback")
    valid = np.isfinite(left) & np.isfinite(right) & (right > 0.0)
    assert not valid.any()
