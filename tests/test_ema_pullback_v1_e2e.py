"""V1.3 end to end (OpenSpec `v1-volume-ratio-v1`, tasks 2.5, 3.1, 3.2): the mean
volume per bar of the pullback over the impulse as `range(ratio(leg_mean, leg_mean))`
through the strategy pipeline on the BTCUSDT.P 5m fixture, band masks, shared nodes
and a spec without a leg mean."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_leg_means import _reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

WINDOW = 12


def _leg(leg: str) -> Spec:
    return {"leg_mean": {"episode": "trend", "leg": leg, "field": "volume"}}


def _branch(low: float | None, high: float | None) -> Spec:
    return {
        "kind": "range",
        "operand": {"ratio": {"left": _leg("pullback"), "right": _leg("impulse")}},
        "min": low,
        "max": high,
        "bounds": "exclusive",
        "empty": "pass",
    }


def _spec(branch: Spec) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    spec["setups"] = [
        {
            "component_id": "composite_setup",
            "instance_id": "v1_branch",
            "params": {
                "children": [{"child_id": "v1", "predicate": branch}],
                "paths": [{"path_id": "pass", "require": ["v1"]}],
            },
        }
    ]
    return spec


def _setup(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _expected(capture: Any, side: str) -> np.ndarray:
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    volume = np.array([float(b.volume) for b in capture.frame.market_bars])
    pullback = _reference(episode, volume, "pullback")
    impulse = _reference(episode, volume, "impulse")
    out = np.full(len(volume), math.nan)
    ok = np.isfinite(pullback) & np.isfinite(impulse) & (impulse > 0)
    out[ok] = pullback[ok] / impulse[ok]
    return out


def test_value_and_band_masks_match_the_research_loop() -> None:
    recorder, context = _run([_variant("probe", _spec(_branch(None, None)))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _setup(capture, side)
        expected = _expected(capture, side)
        values = np.array(
            [math.nan if v is None else v for v in mask.trace["child:v1:value"]], dtype=float
        )
        assert np.isfinite(expected).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-12, equal_nan=True)
        assert all(mask.trace["child:v1"])  # no bounds pass everything
        finite = np.unique(expected[np.isfinite(expected)])
        i, j = int(0.2 * len(finite)), int(0.8 * len(finite))
        low = float((finite[i] + finite[i + 1]) / 2)  # never on a value (the edge is unit-tested)
        high = float((finite[j] + finite[j + 1]) / 2)
        banded, _ = _run([_variant("band", _spec(_branch(low, high)))])
        got = list(_setup(banded.captures[0], side).trace["child:v1"])
        blocked = np.isfinite(expected) & ((expected <= low) | (expected >= high))
        assert got == list((~blocked).tolist())
        assert blocked.any()


def test_candidates_differing_only_in_the_bound_share_the_operands() -> None:
    variants = [_variant(f"c{i}", _spec(_branch(0.1 * (i + 1), None))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.leg_mean") == 4  # impulse and pullback, per side
    assert _calls(context, "predicate.ratio") == 2
    assert _calls(context, "predicate.range") == 4 * 2


def test_static_validation_and_live_history() -> None:
    spec = _spec(_branch(0.23, None))
    check_ema_pullback_static_semantics(spec)
    undeclared = copy.deepcopy(spec)
    undeclared["ema_stack_episode"] = {}
    with pytest.raises(Exception, match="not declared"):
        check_ema_pullback_static_semantics(undeclared)
    requirements = EmaPullbackLiveCalculationRequirements().execute(spec)
    predicate_entries = [item for item in requirements if "predicate" in item.reason]
    assert all(item.bars == 0 for item in predicate_entries)


def test_a_spec_without_a_leg_mean_adds_no_leg_mean_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.leg_mean") == 0
