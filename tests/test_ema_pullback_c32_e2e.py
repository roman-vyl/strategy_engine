"""C3.2 end to end (OpenSpec `c3-previous-depth-ratio-v1`, tasks 2.1, 2.2): the current
pullback depth over the previous one as `ratio(pullback_depth, pullback_depth previous,
right_floor 1e-6)` through the strategy pipeline on the BTCUSDT.P 5m fixture, as a
weighted vote veto, shared nodes and an unchanged current-depth identity."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_pullback_depth import previous_reference, reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

WINDOW = 12
FLOOR = 1e-6
C32 = {
    "ratio": {
        "left": {"pullback_depth": {"episode": "trend"}},
        "right": {"pullback_depth": {"episode": "trend", "touch": "previous"}},
        "right_floor": FLOOR,
    }
}


def _probe(operand: Spec = C32) -> Spec:
    branch = {
        "kind": "range",
        "operand": operand,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "c32", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["c32"]}],
        },
    }


def _veto(level: float) -> Spec:
    step = {"level": level, "veto": True}
    vote_input = {"input_id": "c32", "operand": C32, "direction": "at_least", "steps": [step]}
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "c3", "role": "veto", "inputs": [vote_input]}],
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
    current = reference(episode, low, high)
    previous = previous_reference(episode, low, high)
    out = np.full(len(low), math.nan)
    ok = np.isfinite(current) & np.isfinite(previous) & (previous > FLOOR)
    out[ok] = current[ok] / previous[ok]
    return out


def test_values_and_veto_match_the_research_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:c32:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    i = int(0.8 * len(finite))
    level = float((finite[i] + finite[i + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_veto(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        vetoed = np.isfinite(value) & (value >= level)
        assert vetoed.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~vetoed).tolist())


def test_candidates_differing_only_in_a_level_share_the_operands() -> None:
    variants = [_variant(f"c{i}", _spec(_veto(2.0 + 0.5 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.pullback_depth") == 4  # current and previous, per side
    assert _calls(context, "predicate.ratio") == 2


def test_explicit_current_touch_keeps_the_identity() -> None:
    explicit = {"pullback_depth": {"episode": "trend", "touch": "current"}}
    plain = {"pullback_depth": {"episode": "trend"}}
    variants = [
        _variant("a", _spec(_probe(explicit))),
        _variant("b", _spec(_probe(plain))),
    ]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 2
    assert _calls(context, "predicate.pullback_depth") == 2  # one node per side
