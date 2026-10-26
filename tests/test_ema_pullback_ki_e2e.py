"""kI end to end (OpenSpec `ki-abs-operand-v1`, tasks 2.1, 2.2): a ratio over an absolute
leg change through the strategy pipeline on the BTCUSDT.P 5m fixture, as a range probe and
a weighted vote input, shared nodes and a spec without the operand. The fixture has no open
interest, so the numerator is the pullback close change; open interest is read from the same
market arrays (`test_ema_pullback_leg_change.py`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_leg_change import reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

WINDOW = 12


def _change(leg: str) -> Spec:
    return {"leg_change": {"episode": "trend", "leg": leg, "field": "close"}}


KI = {"ratio": {"left": _change("pullback"), "right": {"abs": _change("impulse")}}}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": KI,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "ki", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["ki"]}],
        },
    }


def _vote(level: float) -> Spec:
    vote_input = {
        "input_id": "ki",
        "operand": KI,
        "direction": "at_most",
        "steps": [{"level": level, "veto": True}],
    }
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "ki", "role": "vote", "inputs": [vote_input]}],
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
    close = np.array([float(b.close) for b in capture.frame.market_bars])
    left = reference(episode, close, "pullback")
    right = np.abs(reference(episode, close, "impulse"))
    out = np.full(len(close), math.nan)
    ok = np.isfinite(left) & np.isfinite(right) & (right > 0)
    out[ok] = left[ok] / right[ok]
    return out


def test_values_and_veto_match_the_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:ki:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    level = float((finite[len(finite) // 5] + finite[len(finite) // 5 + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_vote(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        blocked = np.isfinite(value) & (value <= level)
        assert blocked.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_nodes() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(-1.0 - 0.3 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.abs") == 2  # one per side
    assert _calls(context, "predicate.leg_change") == 4  # impulse and pullback, per side
    assert _calls(context, "predicate.ratio") == 2


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.abs") == 0
