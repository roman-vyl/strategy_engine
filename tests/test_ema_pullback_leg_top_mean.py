"""V1.4 leg top mean operand (OpenSpec `v1-top-volume-ratio-v1`): parsing, the legs
`[S*, P]` and `[P+1, t]`, `k = max(1, ceil(share * L))` in float64, missing cases and
no look-ahead against a loop written like the research reference (`altvals.py` `top10`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.leg_means import leg_top_mean_values


def _top(**fields: Any) -> dict[str, Any]:
    payload = {"episode": "trend", "leg": "pullback", "field": "volume", "share": 0.1}
    return {"leg_top_mean": {**payload, **fields}}


def test_leg_top_mean_parses_as_a_range_and_ratio_operand() -> None:
    operand = _parse(_top()).long.operand.leg_top_mean
    assert (operand.episode, operand.leg, operand.field, operand.share) == (
        "trend",
        "pullback",
        "volume",
        0.1,
    )
    ratio = {"ratio": {"left": _top(), "right": _top(leg="impulse")}}
    assert _parse(ratio).long.operand.ratio.right.leg_top_mean.leg == "impulse"


@pytest.mark.parametrize(
    "fields",
    [
        {"leg": "current"},
        {"field": "close"},
        {"episode": "other"},
        {"share": 0},
        {"share": 1.5},
        {"share": True},
        {"extra": 1},
    ],
)
def test_malformed_leg_top_mean_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_top(**fields))


@pytest.mark.parametrize("missing", ["episode", "leg", "field", "share"])
def test_required_fields(missing: str) -> None:
    operand = _top()
    del operand["leg_top_mean"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_leg_top_mean_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _top(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


def _research_top(x: np.ndarray, share: float) -> float:
    k = max(1, int(np.ceil(share * len(x))))
    return float(np.sort(x)[-k:].mean())


def reference(episode: Any, volume: np.ndarray, leg: str, share: float = 0.1) -> np.ndarray:
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
            out[t] = _research_top(window, share)
    return out


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
@pytest.mark.parametrize("share", [0.1, 0.25, 1.0])
def test_leg_top_mean_matches_the_loop(seed: int, leg: str, share: float) -> None:
    episode, size = _episode(seed)
    volume = np.random.default_rng(seed + 40).uniform(1.0, 50.0, size)
    got = leg_top_mean_values(episode, volume, leg, share)
    expected = reference(episode, volume, leg, share)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0, equal_nan=True)
    assert np.isfinite(got).any() and np.isnan(got).any()


def test_k_is_the_ceiling_of_the_share() -> None:
    assert all(max(1, math.ceil(0.1 * n)) == max(1, -(-n // 10)) for n in range(1, 2000))
    values = np.arange(1.0, 31.0)
    assert _research_top(values, 0.1) == pytest.approx((28 + 29 + 30) / 3)
    assert _research_top(values[: 31 - 20], 0.1) == pytest.approx((10 + 11) / 2)


def test_a_non_finite_volume_in_a_leg_makes_it_missing() -> None:
    episode, size = _episode(1)
    volume = np.full(size, 10.0)
    base = leg_top_mean_values(episode, volume, "impulse", 0.1)
    t = int(np.flatnonzero(np.isfinite(base))[3])
    _, peak, _ = _legs(episode, t) or (0, 0, 0)
    broken = volume.copy()
    broken[peak] = math.nan
    assert math.isnan(leg_top_mean_values(episode, broken, "impulse", 0.1)[t])


@pytest.mark.parametrize("leg", ["impulse", "pullback"])
def test_only_bars_up_to_the_evaluated_bar_are_read(leg: str) -> None:
    episode, size = _episode(4)
    volume = np.random.default_rng(9).uniform(1.0, 50.0, size)
    full = leg_top_mean_values(episode, volume, leg, 0.1)
    for cut in (size // 3, size // 2):
        altered = volume.copy()
        altered[cut + 1 :] *= 7.0
        got = leg_top_mean_values(episode, altered, leg, 0.1)
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])
