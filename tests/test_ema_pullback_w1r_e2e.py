"""W1r end to end (OpenSpec `w1r-nested-ratio-v1`): a ratio whose sides are ratios, through
the strategy pipeline on the BTCUSDT.P 5m fixture with the outer `right_floor`, shared inner
ratios and parsing. The fixture has no open interest, so the numerators are close changes;
open interest is read from the same market arrays (`test_ema_pullback_leg_change.py`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_leg_change import reference
from test_ema_pullback_predicates_a2 import _parse
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.domain.errors import InvalidRequestError

Spec = dict[str, Any]

WINDOW = 12
FLOOR = 0.05


def _change(leg: str) -> Spec:
    return {"leg_change": {"episode": "trend", "leg": leg, "field": "close"}}


# Inner ratios built from close changes only: the impulse over the pullback move and the
# pullback over the impulse move.
INNER_I = {"ratio": {"left": {"abs": _change("impulse")}, "right": {"abs": _change("pullback")}}}
INNER_R = {"ratio": {"left": _change("pullback"), "right": {"abs": _change("impulse")}}}
W1R = {"ratio": {"left": INNER_R, "right": INNER_I, "right_floor": FLOOR}}


def _divide(left: np.ndarray, right: np.ndarray, floor: float) -> np.ndarray:
    out = np.full(len(left), math.nan)
    ok = np.isfinite(left) & np.isfinite(right) & (right > floor)
    out[ok] = left[ok] / right[ok]
    return out


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": W1R,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "w1r", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["w1r"]}],
        },
    }


def _vote(level: float) -> Spec:
    vote_input = {
        "input_id": "w1r",
        "operand": W1R,
        "direction": "at_least",
        "steps": [{"level": level, "veto": True}],
    }
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "w1r", "role": "vote", "inputs": [vote_input]}],
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
    impulse = np.abs(reference(episode, close, "impulse"))
    pullback = np.abs(reference(episode, close, "pullback"))
    inner_i = _divide(impulse, pullback, 0.0)
    inner_r = _divide(reference(episode, close, "pullback"), impulse, 0.0)
    return _divide(inner_r, inner_i, FLOOR)


def test_a_ratio_side_may_be_a_ratio() -> None:
    operand = _parse(W1R).long.operand
    assert operand.ratio.left.ratio is not None and operand.ratio.right.ratio is not None
    assert operand.ratio.right_floor == FLOOR


def test_two_constant_sides_are_still_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"ratio": {"left": {"const": 1.0}, "right": {"const": 2.0}}})


def test_values_and_veto_match_the_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:w1r:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    level = float((finite[4 * len(finite) // 5] + finite[4 * len(finite) // 5 + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_vote(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        blocked = np.isfinite(value) & (value >= level)
        assert blocked.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_inner_ratios() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(1.0 + 0.3 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.ratio") == 6  # two inner and one outer, per side
    assert _calls(context, "predicate.abs") == 4  # impulse and pullback moves, per side
