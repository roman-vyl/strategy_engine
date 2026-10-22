"""V1.1 end to end (OpenSpec `v1-volume-sum-ratio-v1`, tasks 2.2, 3.1, 3.2): the
pullback volume sum over the impulse volume sum as `ratio(leg_sum, leg_sum)` through
the strategy pipeline on the BTCUSDT.P 5m fixture, as a weighted vote input, shared
nodes and a spec without a leg sum."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_leg_sum import _reference
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
    return {"leg_sum": {"episode": "trend", "leg": leg, "field": "volume"}}


V11 = {"ratio": {"left": _leg("pullback"), "right": _leg("impulse")}}


def _vote(weight_level: float, veto_level: float, instance_id: str = "vote") -> Spec:
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": instance_id,
        "params": {
            "threshold": 0.75,
            "voters": [
                {
                    "voter_id": "v1",
                    "role": "vote",
                    "inputs": [
                        {
                            "input_id": "v11",
                            "operand": V11,
                            "direction": "at_most",
                            "steps": [
                                {"level": weight_level, "weight": 0.6618},
                                {"level": veto_level, "veto": True},
                            ],
                        }
                    ],
                }
            ],
        },
    }


def _spec(*setups: Spec) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    spec["setups"] = list(setups)
    return spec


def _mask(capture: Any, side: str) -> Any:
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


def _levels(expected: np.ndarray) -> tuple[float, float]:
    finite = np.unique(expected[np.isfinite(expected)])
    i, j = int(0.1 * len(finite)), int(0.3 * len(finite))
    # between two values, so float noise cannot move an entry across a level
    return float((finite[i] + finite[i + 1]) / 2), float((finite[j] + finite[j + 1]) / 2)


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": V11,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "v11", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["v11"]}],
        },
    }


def test_values_and_vote_match_the_research_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        values = np.array(
            [math.nan if v is None else v for v in _mask(capture, side).trace["child:v11:value"]],
            dtype=float,
        )
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    veto, weight = _levels(expected["long"])
    recorder, context = _run([_variant("vote", _spec(_vote(weight, veto)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        finite = np.isfinite(value)
        vetoed = finite & (value <= veto)
        assert vetoed.any() and (finite & (value <= weight) & ~vetoed).any()
        # 0.6618 alone stays under 0.75: only the veto step blocks
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~vetoed).tolist())


def test_candidates_differing_only_in_a_level_share_the_operands() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(0.05 + 0.01 * i, 0.04))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.leg_sum") == 4  # impulse and pullback, per side
    assert _calls(context, "predicate.ratio") == 2


def test_static_validation_and_live_history() -> None:
    spec = _spec(_vote(0.0574, 0.0441))
    check_ema_pullback_static_semantics(spec)
    requirements = EmaPullbackLiveCalculationRequirements().execute(spec)
    assert requirements


def test_a_spec_without_a_leg_sum_adds_no_leg_sum_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.leg_sum") == 0
