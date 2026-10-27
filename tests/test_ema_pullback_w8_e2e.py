"""W8_d end to end (OpenSpec `w8-rolling-extreme-v1`, task 3.1): a base-bar field over its
rolling maximum through the strategy pipeline on the BTCUSDT.P 5m fixture, as a range
probe and a vote veto, with shared nodes. The fixture has no open interest, so the field
is `close`; open interest is the same column path (`test_rolling_extreme.py`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

PERIOD = 96
W8 = {
    "ratio": {
        "left": {"price": "close"},
        "right": {
            "feature": {"kind": "rolling_max", "source": "close", "params": {"period": PERIOD}}
        },
    }
}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": W8,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "w8", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["w8"]}],
        },
    }


def _vote(level: float) -> Spec:
    vote_input = {
        "input_id": "w8",
        "operand": W8,
        "direction": "at_most",
        "steps": [{"level": level, "veto": True}],
    }
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "w8", "role": "vote", "inputs": [vote_input]}],
        },
    }


def _spec(*setups: Spec) -> Spec:
    spec = base_spec()
    spec["setups"] = list(setups)
    return spec


def _mask(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _expected(capture: Any) -> np.ndarray:
    close = np.array([float(b.close) for b in capture.frame.market_bars])
    out = np.full(len(close), math.nan)
    for t in range(PERIOD - 1, len(close)):
        out[t] = close[t] / close[t - PERIOD + 1 : t + 1].max()
    return out


def test_values_and_veto_match_the_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = _expected(capture)
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:w8:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        np.testing.assert_allclose(values, expected, rtol=1e-12, equal_nan=True)
    finite = np.sort(expected[np.isfinite(expected)])
    level = float(finite[len(finite) // 5])
    recorder, context = _run([_variant("vote", _spec(_vote(level)))])
    assert context.stats.unforeseen_consumptions == 0
    blocked = np.isfinite(expected) & (expected <= level)
    assert blocked.any()
    for side in ("long", "short"):
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_feature() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(0.95 + 0.01 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "indicator.rolling_max") == 1
