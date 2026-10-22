"""C3.1 end to end (OpenSpec `c3-pullback-depth-share-v1`, tasks 2.1, 2.2): the pullback
depth as a share of the impulse height through the strategy pipeline on the BTCUSDT.P 5m
fixture, as a weighted vote input, shared nodes and a spec without the operand."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_pullback_depth import reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

WINDOW = 12
C31 = {"pullback_depth": {"episode": "trend"}}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": C31,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "c31", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["c31"]}],
        },
    }


def _vote(level: float) -> Spec:
    step = {"level": level, "weight": 0.8}
    vote_input = {"input_id": "c31", "operand": C31, "direction": "at_least", "steps": [step]}
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "c3", "role": "vote", "inputs": [vote_input]}],
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
    low = np.array([float(b.low) for b in capture.frame.market_bars])
    high = np.array([float(b.high) for b in capture.frame.market_bars])
    return reference(episode, low, high)


def test_values_and_vote_match_the_research_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:c31:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    i = int(0.7 * len(finite))
    level = float((finite[i] + finite[i + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_vote(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        blocked = np.isfinite(value) & (value >= level)
        assert blocked.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_operand() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(0.3 + 0.1 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.pullback_depth") == 2  # one per side


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.pullback_depth") == 0
