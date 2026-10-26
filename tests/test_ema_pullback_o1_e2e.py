"""O1 end to end (OpenSpec `o1-leg-change-v1`, tasks 2.1, 2.2): the leg change operand
through the strategy pipeline on the BTCUSDT.P 5m fixture as a weighted vote input with
a weight step and a veto step, shared nodes and a spec without the operand. The fixture
has no open interest, so the pipeline is checked on `close`; open interest is read from
the same market arrays (`test_ema_pullback_leg_change.py`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_leg_change import reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

WINDOW = 12


def _operand(leg: str = "impulse", touch: str = "current") -> Spec:
    return {"leg_change": {"episode": "trend", "leg": leg, "field": "close", "touch": touch}}


def _probe(operand: Spec) -> Spec:
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
            "children": [{"child_id": "o1", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["o1"]}],
        },
    }


def _vote(weight_level: float, veto_level: float, threshold: float = 0.75) -> Spec:
    steps = [{"level": weight_level, "weight": 0.3891}, {"level": veto_level, "veto": True}]
    vote_input = {"input_id": "o1", "operand": _operand(), "direction": "at_most", "steps": steps}
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": threshold,
            "voters": [{"voter_id": "o1", "role": "vote", "inputs": [vote_input]}],
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


def _expected(capture: Any, side: str, leg: str = "impulse", touch: str = "current") -> np.ndarray:
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    close = np.array([float(b.close) for b in capture.frame.market_bars])
    return reference(episode, close, leg, touch)


@pytest.mark.parametrize(
    ("leg", "touch"), [("impulse", "current"), ("pullback", "current"), ("impulse", "previous")]
)
def test_values_match_the_loop(leg: str, touch: str) -> None:
    probe, _ = _run([_variant("probe", _spec(_probe(_operand(leg, touch))))])
    (capture,) = probe.captures
    for side in ("long", "short"):
        expected = _expected(capture, side, leg, touch)
        trace = _mask(capture, side).trace["child:o1:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-12, equal_nan=True)


def test_weight_and_veto_steps() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe(_operand())))])
    expected = {side: _expected(probe.captures[0], side) for side in ("long", "short")}
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    high, low = (
        float((finite[i] + finite[i + 1]) / 2)
        for i in (int(0.4 * len(finite)), int(0.1 * len(finite)))
    )
    for threshold, level in ((0.3, high), (0.75, low)):
        # 0.3: the weight step alone blocks; 0.75: only the veto step blocks.
        recorder, context = _run([_variant("vote", _spec(_vote(high, low, threshold)))])
        assert context.stats.unforeseen_consumptions == 0
        for side in ("long", "short"):
            value = expected[side]
            blocked = np.isfinite(value) & (value <= level)
            assert blocked.any()
            allowed = _mask(recorder.captures[0], side).local_setup_allowed
            assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_operand() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(-1.0 - 0.3 * i, -5.0))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.leg_change") == 2  # one per side


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.leg_change") == 0
