"""Independent endpoint references and integration for interval-series-operands-v1."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant
from test_ema_pullback_ema_slope_e2e import _branch, _ema, _mask, _spec, _trace
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse
from test_ema_pullback_stack_episode_e2e import _run

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import _predicate_history
from strategy_engine.strategies.ema_pullback.predicates import (
    Interval,
    interval_change_values,
    operand_needs_episode,
    resolve_predicate,
)


def interval(
    of: dict[str, Any], span: dict[str, Any], op: str = "relative_change_per_bar"
) -> dict[str, Any]:
    return {"interval_change": {"of": of, "interval": span, "operation": op}}


def scaled(op: dict[str, Any], factor: float = 1e4) -> dict[str, Any]:
    return {"scale": {"operand": op, "factor": factor}}


def test_fixed_endpoint_inclusion_missing_and_negative_base() -> None:
    x = np.array([-2.0, np.nan, -4.0, 0.0, 8.0, np.inf])
    span = Interval("fixed", bars=2)
    np.testing.assert_allclose(
        interval_change_values(x, span, "change"),
        [np.nan, np.nan, -2, np.nan, 12, np.nan],
        equal_nan=True,
    )
    np.testing.assert_allclose(
        interval_change_values(x, span, "relative_change_per_bar"),
        [np.nan, np.nan, 0.5, np.nan, -1.5, np.nan],
        equal_nan=True,
    )
    assert not interval_change_values(x, span, "change").flags.writeable
    assert len(interval_change_values(np.array([]), span, "change")) == 0


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
@pytest.mark.parametrize("last_n", [None, 3, 100])
@pytest.mark.parametrize(
    "operation", ["change", "change_per_bar", "relative_change", "relative_change_per_bar"]
)
def test_episode_independent_reference(
    side: str, leg: str, last_n: int | None, operation: str
) -> None:
    episode, size = _episode(17)
    episode = replace(episode, side=side)
    x = 20 + np.sin(np.arange(size) / 4) + np.arange(size) / 50
    x[::29] = np.nan
    span = Interval("episode", ref="trend", leg=leg, last_n=last_n)
    actual = interval_change_values(x, span, operation, episode)
    expected = np.full(size, np.nan)
    for t in range(size):
        points = _legs(episode, t)
        if points is None:
            continue
        s, p, _ = points
        a, b = (s, p) if leg == "impulse" else (p, t)
        if last_n is not None:
            a = max(a, b - last_n)
        if a < 0 or b > t or a >= b or not np.isfinite(x[[a, b]]).all():
            continue
        y = x[b] - x[a]
        if operation.startswith("relative"):
            y /= x[a]
        if operation.endswith("per_bar"):
            y /= b - a
        expected[t] = y
    np.testing.assert_allclose(actual, expected, equal_nan=True)
    assert np.isfinite(actual).sum() > 10
    # Future prices cannot influence an already evaluated interval.
    changed = x.copy()
    changed[size // 2 :] = 123456.0
    np.testing.assert_allclose(
        interval_change_values(changed, span, operation, episode)[: size // 2],
        actual[: size // 2],
        equal_nan=True,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "fixed", "bars": 0},
        {"kind": "fixed", "bars": True},
        {"kind": "fixed", "bars": 2, "ref": "trend"},
        {"kind": "episode", "ref": "missing", "leg": "impulse"},
        {"kind": "episode", "ref": "trend", "leg": "previous"},
        {"kind": "episode", "ref": "trend", "leg": "impulse", "last_n": None},
    ],
)
def test_invalid_intervals(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(interval({"price": "close"}, bad))


@pytest.mark.parametrize(
    "bad",
    [
        {"const": 3},
        {"signed": {"operand": {"price": "close"}, "center": 0}},
        {"feature": {**_ema(5), "timeframe": "1h"}},
        interval({"price": "close"}, {"kind": "fixed", "bars": 1}),
        {"difference": {"left": {"const": 1}, "right": {"const": 2}}},
    ],
)
def test_bounded_series(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(interval(bad, {"kind": "fixed", "bars": 2}))


def test_identity_and_history() -> None:
    fixed = _parse(scaled(interval({"price": "close"}, {"kind": "fixed", "bars": 24})))
    assert not operand_needs_episode(fixed.long.operand)
    assert _predicate_history(fixed, "test")[0].bars == 24
    assert resolve_predicate(fixed, {}, "long") == resolve_predicate(fixed, {}, "short")
    other = _parse(scaled(interval({"price": "close"}, {"kind": "fixed", "bars": 25})))
    assert resolve_predicate(fixed, {}, "long") != resolve_predicate(other, {}, "long")
    raw = {"left": {"price": "close"}, "right": {"price": "open"}, "right_floor": -0.2}
    old = resolve_predicate(_parse({"ratio": raw}), {}, "long")
    explicit = resolve_predicate(
        _parse({"ratio": {**raw, "denominator_mode": "positive"}}), {}, "long"
    )
    assert old == explicit
    with pytest.raises(InvalidRequestError):
        _parse({"ratio": {**raw, "denominator_mode": "absolute"}})


def test_pipeline_arithmetic_series_and_shared_nodes() -> None:
    e = {"feature": _ema(50)}
    gap = {
        "ratio": {
            "left": {"difference": {"left": e, "right": {"feature": _ema(100)}}},
            "right": {"feature": _ema(100)},
        }
    }
    fixed = scaled(interval(e, {"kind": "fixed", "bars": 24}))
    clipped = scaled(
        interval(e, {"kind": "episode", "ref": "trend", "leg": "pullback", "last_n": 24})
    )
    velocity = scaled(interval(gap, {"kind": "fixed", "bars": 12}, "change_per_bar"))
    ops = {
        "fixed": fixed,
        "same": fixed,
        "clipped": clipped,
        "gap": velocity,
        "e50": scaled(e, 1),
        "e100": scaled({"feature": _ema(100)}, 1),
        "negative": {"ratio": {"left": e, "right": {"const": -2}, "denominator_mode": "absolute"}},
        "floor": {
            "ratio": {
                "left": e,
                "right": {"const": -2},
                "denominator_mode": "absolute",
                "right_floor": 2,
            }
        },
        "legacy": {"ratio": {"left": e, "right": {"const": -2}}},
    }
    children = [{"child_id": k, "predicate": _branch(v)} for k, v in ops.items()]
    setup = {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {"children": children, "paths": [{"path_id": "pass", "require": list(ops)}]},
    }
    recorder, context = _run([_variant("probe", _spec(setup)), _variant("repeat", _spec(setup))])
    assert context.stats.unforeseen_consumptions == 0
    for capture in recorder.captures:
        for side in ("long", "short"):
            mask = _mask(capture, side)
            e50, e100 = _trace(mask, "e50"), _trace(mask, "e100")
            expected = np.full(len(e50), np.nan)
            expected[24:] = (e50[24:] - e50[:-24]) / e50[:-24] / 24 * 1e4
            np.testing.assert_allclose(_trace(mask, "fixed"), expected, equal_nan=True)
            np.testing.assert_allclose(_trace(mask, "same"), expected, equal_nan=True)
            g = (e50 - e100) / e100
            expected_gap = np.full(len(g), np.nan)
            expected_gap[12:] = (g[12:] - g[:-12]) / 12 * 1e4
            np.testing.assert_allclose(_trace(mask, "gap"), expected_gap, equal_nan=True)
            np.testing.assert_allclose(_trace(mask, "negative"), -e50 / 2, equal_nan=True)
            assert np.isnan(_trace(mask, "floor")).all()
            assert np.isnan(_trace(mask, "legacy")).all()
            assert np.any(np.abs(_trace(mask, "fixed") - _trace(mask, "clipped")) > 1e-6)


@pytest.mark.parametrize("factor", [True, float("inf"), float("nan"), "2"])
def test_scale_rejects_invalid_factor(factor: Any) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(scaled({"price": "close"}, factor))


def test_scale_missing_survives_zero_and_overflow() -> None:
    from types import SimpleNamespace

    from strategy_engine.strategies.ema_pullback.predicates import _values

    f = {"feature": _ema(2)}
    for factor, expected in [(0, [0, np.nan, np.nan]), (1e308, [np.nan, np.nan, np.nan])]:
        pred = _parse(scaled(f, factor))
        feature = pred.features()[0]
        frame = SimpleNamespace(
            time_ms=np.arange(3), series={feature.output_id: [2.0, np.nan, np.inf]}
        )
        np.testing.assert_allclose(
            _values(pred.long.operand, frame, None, None, "long", None), expected, equal_nan=True
        )


def test_ratio_absolute_floor_and_legacy_negative_floor() -> None:
    from types import SimpleNamespace

    from strategy_engine.strategies.ema_pullback.predicates import Operand, Ratio, _ratio_operand

    feature = _parse({"feature": _ema(2)}).features()[0]
    frame = SimpleNamespace(
        time_ms=np.arange(7),
        series={feature.output_id: [-2.0, -0.02, 0.0, 0.02, 2.0, np.nan, np.inf]},
    )
    absolute = Ratio(Operand(const=1), Operand(feature=feature), 0.02, "absolute")
    np.testing.assert_allclose(
        _ratio_operand(absolute, frame, None, None, "long", None, "operand"),
        [-0.5, np.nan, np.nan, np.nan, 0.5, np.nan, np.nan],
        equal_nan=True,
    )
    legacy = Ratio(Operand(const=1), Operand(feature=feature), -3)
    np.testing.assert_allclose(
        _ratio_operand(legacy, frame, None, None, "long", None, "operand"),
        [-0.5, -50, np.inf, 50, 0.5, np.nan, np.nan],
        equal_nan=True,
    )


def test_live_warmup_adds_fixed_window_and_keeps_historical_peak_horizon() -> None:
    import pandas as pd
    from test_live_calculation_plan_window import _minimal_spec, _plan

    from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
        EmaPullbackLiveCalculationRequirements,
    )
    from strategy_engine.strategies.live_calculation.indicator_requirements import ema_warmup_bars
    from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart

    fixed = interval({"feature": _ema(50)}, {"kind": "fixed", "bars": 96})
    pred = _parse(fixed)
    setup = {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "probe", "predicate": _branch(fixed)}],
            "paths": [{"path_id": "pass", "require": ["probe"]}],
        },
    }
    spec = _minimal_spec(setups=[setup])
    anchor = 10000 * 300000
    plan = PlanLiveHistoryStart(strategy_requirements=EmaPullbackLiveCalculationRequirements())
    window = plan.execute(
        raw_spec=spec,
        indicator_plan=_plan(*pred.features()),
        base_timeframe="5m",
        history_anchor_open_time_ms=anchor,
    )
    warm = ema_warmup_bars(50)
    assert window.from_ms == anchor - (warm + 96) * 300000
    # Same endpoint measurement with fully warmed versus bounded EMA prefix.
    x = 100 + np.sin(np.arange(10100) / 30)
    start = window.from_ms // 300000
    full = pd.Series(x).ewm(span=50, adjust=False).mean().to_numpy()
    prefix = pd.Series(x[start:]).ewm(span=50, adjust=False).mean().to_numpy()
    span = Interval("fixed", bars=96)
    a = interval_change_values(full, span, "relative_change_per_bar")[10000:]
    b = interval_change_values(prefix, span, "relative_change_per_bar")[10000 - start :]
    assert np.array_equal(np.isfinite(a), np.isfinite(b))
    # Bound from the existing EMA seed-decay policy, not fitted to this result:
    # price and EMA in [99,101], initial seed error <= 2, both endpoints warmed.
    seed_error = 2 * (1 - 2 / 51) ** warm
    bound = seed_error * (1 / 99 + 101 / 99**2) / 96
    np.testing.assert_allclose(a, b, atol=bound, rtol=0)
    episode = interval(
        {"feature": _ema(50)}, {"kind": "episode", "ref": "trend", "leg": "impulse", "last_n": 3}
    )
    assert _predicate_history(_parse(episode), "p", {"trend": 2500})[0].bars == 2500
    at = {"at_point": {"episode": "trend", "point": "peak", "operand": fixed}}
    assert _predicate_history(_parse(at), "p", {"trend": 2500})[0].bars == 2596


def test_new_operand_in_weighted_vote_and_batch() -> None:
    from test_ema_pullback_ema_slope_e2e import _vote

    op = scaled(interval({"feature": _ema(50)}, {"kind": "fixed", "bars": 24}))
    vote = _vote(0)
    vote["params"]["voters"][0]["inputs"][0]["operand"] = op
    recorder, context = _run([_variant("vote", _spec(vote)), _variant("same", _spec(vote))])
    assert context.stats.unforeseen_consumptions == 0
    assert len(recorder.captures) == 2
    separate, _ = _run([_variant("vote", _spec(vote))], memo_enabled=False)
    for side in ("long", "short"):
        a = _mask(recorder.captures[0], side)
        b = _mask(recorder.captures[1], side)
        assert a.trace == b.trace == _mask(separate.captures[0], side).trace


@pytest.mark.parametrize(
    "name", ["fixed-ema-slope", "normalized-gap-velocity", "impulse-slope-ratio"]
)
def test_documented_specs_execute(name: str) -> None:
    import json
    from pathlib import Path

    spec = json.loads(
        (Path(__file__).parents[1] / "examples/interval-series" / f"{name}.json").read_text()
    )
    recorder, context = _run([_variant(name, spec)])
    assert len(recorder.captures) == 1
    assert context.stats.unforeseen_consumptions == 0
