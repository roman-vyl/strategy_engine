"""B3 end to end (OpenSpec `b3-impulse-atr-v1`, tasks 2.1, 2.2): the impulse height over
the rolling-mean ATR on the peak bar through the strategy pipeline on the BTCUSDT.P 5m
fixture, as a weighted vote input with a weight step and a veto step, shared nodes and a
spec without the operand."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from parity.corpus import _variant, base_spec
from test_ema_pullback_impulse_atr import reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.indicators.implementations.atr import atr_rolling_mean

Spec = dict[str, Any]

WINDOW = 12
PERIOD = 48
B3 = {"impulse_atr": {"episode": "trend", "atr": {"kind": "atr", "params": {"period": PERIOD}}}}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": B3,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "b3", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["b3"]}],
        },
    }


def _vote(weight_level: float, veto_level: float, threshold: float = 0.75) -> Spec:
    steps = [{"level": weight_level, "weight": 0.32}, {"level": veto_level, "veto": True}]
    vote_input = {"input_id": "b3", "operand": B3, "direction": "at_most", "steps": steps}
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": threshold,
            "voters": [{"voter_id": "b3", "role": "vote", "inputs": [vote_input]}],
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
    series = {k: pd.Series([float(getattr(b, k)) for b in bars]) for k in ("high", "low", "close")}
    atr = atr_rolling_mean(series["high"], series["low"], series["close"], period=PERIOD)
    return reference(episode, atr.to_numpy(dtype=float))


def test_values_weight_and_veto_match_the_research_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _expected(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:b3:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    low, high = (
        float((finite[i] + finite[i + 1]) / 2)
        for i in (int(0.1 * len(finite)), int(0.4 * len(finite)))
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
    variants = [_variant(f"c{i}", _spec(_vote(9.0 + i, 4.65))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.impulse_atr") == 2  # one per side


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.impulse_atr") == 0
