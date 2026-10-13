"""V2.2 force fields of the leg mean operand (OpenSpec `v2-force-ratio-v1`):
the side-signed candle force, its leg means against a loop written like the
research reference (`v2_engine_ref.py`), the ratio filter, missing cases and
no look-ahead."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.leg_means import (
    force_series,
    leg_bar_counts,
    leg_mean_values,
)
from strategy_engine.strategies.ema_pullback.predicates import _range_mask


def _force(field: str, leg: str = "pullback") -> dict[str, Any]:
    return {"leg_mean": {"episode": "trend", "leg": leg, "field": field}}


def _market(seed: int, size: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, size))
    volume = rng.uniform(1.0, 50.0, size)
    return close, volume


@pytest.mark.parametrize("field", ["force_with", "force_against"])
def test_force_fields_parse(field: str) -> None:
    assert _parse(_force(field)).long.operand.leg_mean.field == field


def test_other_fields_are_still_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_force("force"))


def test_force_series_signs_and_first_bar() -> None:
    close = np.array([10.0, 12.0, 11.0])
    volume = np.array([5.0, 3.0, 4.0])
    raw = np.array([0.0, 6.0, -4.0])  # (close[u] - close[u-1]) * volume[u]
    np.testing.assert_array_equal(force_series(close, volume, "force_with", "long"), raw)
    np.testing.assert_array_equal(force_series(close, volume, "force_against", "long"), -raw)
    np.testing.assert_array_equal(force_series(close, volume, "force_with", "short"), -raw)
    np.testing.assert_array_equal(force_series(close, volume, "force_against", "short"), raw)


def test_long_and_short_examples() -> None:
    close = np.array([100.0, 99.0, 101.0])
    volume = np.array([7.0, 10.0, 10.0])
    # a pullback bar that closes 1 below the previous close on volume 10
    assert force_series(close, volume, "force_against", "long")[1] == 10.0
    assert force_series(close, volume, "force_with", "long")[1] == -10.0
    # a short: a bar that closes 2 above the previous close on volume 10
    assert force_series(close, volume, "force_against", "short")[2] == 20.0


def test_a_non_finite_input_makes_the_bar_non_finite() -> None:
    close = np.array([1.0, 2.0, math.nan, 4.0, 5.0])
    volume = np.array([1.0, 1.0, 1.0, math.nan, 1.0])
    out = force_series(close, volume, "force_with", "long")
    assert out[0] == 0.0 and out[1] == 1.0
    assert np.isnan(out[2:4]).all() and out[4] == 1.0


def _reference(
    episode: Any, close: np.ndarray, volume: np.ndarray, side: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = 1.0 if side == "long" else -1.0
    force = np.zeros(len(close))
    force[1:] = (close[1:] - close[:-1]) * volume[1:]
    imp = np.full(len(close), math.nan)
    pb = np.full(len(close), math.nan)
    value = np.full(len(close), math.nan)
    for t in range(len(close)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak < t):
            continue
        imp[t] = g * force[origin : peak + 1].sum() / (peak - origin + 1)
        pb[t] = -g * force[peak + 1 : t + 1].sum() / (t - peak)
        if imp[t] > 0:
            value[t] = pb[t] / imp[t]
    return imp, pb, value


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
def test_leg_means_and_ratio_match_the_loop(seed: int, side: str) -> None:
    episode, size = _episode(seed)
    close, volume = _market(seed + 70, size)
    imp = leg_mean_values(episode, force_series(close, volume, "force_with", side), "impulse")
    pb = leg_mean_values(episode, force_series(close, volume, "force_against", side), "pullback")
    expected_imp, expected_pb, expected_value = _reference(episode, close, volume, side)
    np.testing.assert_allclose(
        imp[np.isfinite(expected_imp)], expected_imp[np.isfinite(expected_imp)], rtol=1e-12
    )
    np.testing.assert_allclose(pb, expected_pb, rtol=1e-12, equal_nan=True)
    ok = np.isfinite(imp) & np.isfinite(pb) & (imp > 0.0)
    value = np.where(ok, pb / np.where(ok, imp, 1.0), math.nan)
    np.testing.assert_allclose(value, expected_value, rtol=1e-12, equal_nan=True)
    assert np.isfinite(value).any()


def test_values_cover_negative_and_non_positive_impulse() -> None:
    seen_negative = seen_empty = False
    for seed in range(12):
        episode, size = _episode(seed % 6)
        close, volume = _market(seed + 5, size)
        imp = leg_mean_values(episode, force_series(close, volume, "force_with", "long"), "impulse")
        pb = leg_mean_values(
            episode, force_series(close, volume, "force_against", "long"), "pullback"
        )
        ok = np.isfinite(imp) & np.isfinite(pb)
        seen_empty |= bool((ok & (imp <= 0)).any())
        seen_negative |= bool((ok & (imp > 0) & (pb < 0)).any())
    assert seen_negative and seen_empty


def test_pullback_starts_after_the_peak_and_is_missing_at_the_peak() -> None:
    episode, size = _episode(2)
    close, volume = _market(3, size)
    series = force_series(close, volume, "force_against", "long")
    pullback = leg_mean_values(episode, series, "pullback")
    checked = 0
    for t in range(size):
        legs = _legs(episode, t)
        if legs is None or not legs[0] <= legs[1] <= t:
            continue
        peak = legs[1]
        if t == peak:
            assert math.isnan(pullback[t])
        else:
            assert pullback[t] == pytest.approx(series[peak + 1 : t + 1].mean())
            checked += 1
    assert checked


def test_the_first_impulse_bar_reads_the_close_before_the_origin() -> None:
    episode, size = _episode(1)
    close, volume = _market(8, size)
    series = force_series(close, volume, "force_with", "long")
    impulse = leg_mean_values(episode, series, "impulse")
    t = int(np.flatnonzero(np.isfinite(impulse))[2])
    origin, peak, _ = _legs(episode, t) or (0, 0, 0)
    expected = np.mean(
        [(close[u] - close[u - 1]) * volume[u] for u in range(max(origin, 1), peak + 1)]
        if origin
        else [0.0] + [(close[u] - close[u - 1]) * volume[u] for u in range(1, peak + 1)]
    )
    assert impulse[t] == pytest.approx(expected)


def test_a_non_finite_close_in_a_leg_makes_it_missing() -> None:
    episode, size = _episode(1)
    close, volume = _market(2, size)
    base = leg_mean_values(episode, force_series(close, volume, "force_with", "long"), "impulse")
    t = int(np.flatnonzero(np.isfinite(base))[3])
    _, peak, _ = _legs(episode, t) or (0, 0, 0)
    broken = close.copy()
    broken[peak] = math.nan
    series = force_series(broken, volume, "force_with", "long")
    assert math.isnan(leg_mean_values(episode, series, "impulse")[t])


def test_only_bars_up_to_the_evaluated_bar_are_read() -> None:
    episode, size = _episode(4)
    close, volume = _market(9, size)
    full = leg_mean_values(
        episode, force_series(close, volume, "force_against", "short"), "pullback"
    )
    for cut in (size // 3, size // 2):
        altered_close = close.copy()
        altered_close[cut + 1 :] += 50.0
        altered_volume = volume.copy()
        altered_volume[cut + 1 :] *= 7.0
        got = leg_mean_values(
            episode,
            force_series(altered_close, altered_volume, "force_against", "short"),
            "pullback",
        )
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


def _band(low: float | None, high: float | None) -> Any:
    cond = _parse(_force("force_with")).long
    return type(cond)(cond.operand, low, high, "exclusive", "pass")


def test_thresholds_are_inclusive_negative_values_stay_and_missing_passes() -> None:
    values = np.array([-0.5, 0.0, 0.007, 5.0, 10.0, 16.0, math.nan])
    assert _range_mask(_band(None, 10.0), values).tolist() == [
        True,
        True,
        True,
        True,
        False,
        False,
        True,
    ]
    assert _range_mask(_band(0.0, None), values).tolist() == [
        False,
        False,
        True,
        True,
        True,
        True,
        True,
    ]
    assert _range_mask(_band(0.007, 10.0), values).tolist() == [
        False,
        False,
        False,
        True,
        False,
        False,
        True,
    ]
    assert _range_mask(_band(None, None), values).all()


def test_an_empty_pullback_and_a_non_positive_impulse_are_missing() -> None:
    imp = np.array([1.0, 0.0, -2.0, math.nan, 2.0])
    pb = np.array([math.nan, 3.0, 3.0, 3.0, 4.0])
    ok = np.isfinite(imp) & np.isfinite(pb) & (imp > 0.0)
    value = np.where(ok, pb / np.where(ok, imp, 1.0), math.nan)
    assert np.isnan(value[:4]).all() and value[4] == 2.0
    assert _range_mask(_band(0.5, 3.0), value).tolist() == [True] * 5


@pytest.mark.parametrize("seed", range(4))
def test_leg_sums_are_mean_times_count(seed: int) -> None:
    episode, size = _episode(seed)
    close, volume = _market(seed + 30, size)
    series = force_series(close, volume, "force_with", "long")
    for leg in ("impulse", "pullback"):
        mean = leg_mean_values(episode, series, leg)
        count = leg_bar_counts(episode, size, leg)
        for t in np.flatnonzero(np.isfinite(mean)):
            legs = _legs(episode, int(t))
            origin, peak, _ = legs
            begin, end = (origin, peak) if leg == "impulse" else (peak + 1, int(t))
            assert count[t] == end - begin + 1
            assert mean[t] * count[t] == pytest.approx(series[begin : end + 1].sum())
