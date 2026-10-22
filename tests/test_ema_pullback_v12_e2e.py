"""V1.2 end to end (OpenSpec `v1-own-color-volume-ratio-v1`, tasks 2.1, 2.2): the
own colour volume of the pullback over that of the impulse as
`ratio(leg_sum, leg_sum)` through the strategy pipeline on the BTCUSDT.P 5m fixture,
as a weighted vote veto, and shared nodes."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_leg_sum import _reference, own_color_reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

WINDOW = 12


def _leg(leg: str) -> Spec:
    return {"leg_sum": {"episode": "trend", "leg": leg, "field": "own_color_volume"}}


V12 = {"ratio": {"left": _leg("pullback"), "right": _leg("impulse")}}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": V12,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "v12", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["v12"]}],
        },
    }


def _veto(level: float) -> Spec:
    step = {"level": level, "veto": True}
    vote_input = {"input_id": "v12", "operand": V12, "direction": "at_most", "steps": [step]}
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "v1", "role": "veto", "inputs": [vote_input]}],
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
    bars = capture.frame.market_bars
    open_ = np.array([float(b.open) for b in bars])
    close = np.array([float(b.close) for b in bars])
    volume = np.array([float(b.volume) for b in bars])
    legs = {}
    for leg in ("impulse", "pullback"):
        series = own_color_reference(open_, close, volume, side, leg)
        legs[leg] = _reference(episode, series, leg)
    out = np.full(len(volume), math.nan)
    ok = np.isfinite(legs["pullback"]) & np.isfinite(legs["impulse"]) & (legs["impulse"] > 0)
    out[ok] = legs["pullback"][ok] / legs["impulse"][ok]
    return out


def test_values_and_veto_match_the_research_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:v12:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    i = int(0.2 * len(finite))
    level = float((finite[i] + finite[i + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_veto(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        vetoed = np.isfinite(value) & (value <= level)
        assert vetoed.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~vetoed).tolist())


def test_candidates_differing_only_in_a_level_share_the_operands() -> None:
    variants = [_variant(f"c{i}", _spec(_veto(0.02 + 0.01 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.leg_sum") == 4  # impulse and pullback, per side
    assert _calls(context, "predicate.ratio") == 2
