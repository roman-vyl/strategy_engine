"""D1 end to end (OpenSpec `d1-forming-candle-v1`, tasks 2.1, 2.2): the forming UTC day
candle over the Wilder ATR14 of the previous day through the strategy pipeline on the
BTCUSDT.P 5m fixture, computed like research `tf_frame(1440)`, as a weighted vote input
with a weight step and a veto step, shared nodes and a spec without the operand."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from parity.corpus import _variant, base_spec
from test_ema_pullback_predicates_a2 import _legs
from test_ema_pullback_stack_episode_e2e import _calls, _run

Spec = dict[str, Any]

WINDOW = 12
DAY_MS = 86_400_000
D1 = {
    "forming_candle": {
        "episode": "trend",
        "timeframe": "1d",
        "atr": {"kind": "atr_wilder", "timeframe": "1d", "params": {"period": 14}},
    }
}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": D1,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "d1", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["d1"]}],
        },
    }


def _vote(weight_level: float, veto_level: float, threshold: float = 0.75) -> Spec:
    steps = [{"level": weight_level, "weight": 0.8564}, {"level": veto_level, "veto": True}]
    vote_input = {"input_id": "d1", "operand": D1, "direction": "at_most", "steps": steps}
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": threshold,
            "voters": [{"voter_id": "d1", "role": "vote", "inputs": [vote_input]}],
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


def _research(capture: Any, side: str) -> np.ndarray:
    """`altvals.py` `tf_frame(1440)` and `d1`, with the ATR warm-up as the only day gate."""

    bars = capture.frame.market_bars
    time_ms = np.array([int(b.open_time_ms) for b in bars], dtype=np.int64)
    o, h, lo, c = (
        np.array([float(getattr(b, k)) for b in bars]) for k in ("open", "high", "low", "close")
    )
    day = time_ms // DAY_MS
    first = np.r_[True, day[1:] != day[:-1]]
    idx = np.cumsum(first) - 1
    k = int(idx[-1]) + 1
    dh, dl, dc = np.full(k, -np.inf), np.full(k, np.inf), np.zeros(k)
    np.maximum.at(dh, idx, h)
    np.minimum.at(dl, idx, lo)
    dc[idx] = c
    pc = np.r_[np.nan, dc[:-1]]
    tr = np.nanmax(np.c_[dh - dl, np.abs(dh - pc), np.abs(dl - pc)], axis=1)
    atr = np.full(k, np.nan)
    atr[13] = np.mean(tr[:14])
    for i in range(14, k):
        atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
    day_open = o[np.flatnonzero(first)][idx]
    g = 1.0 if side == "long" else -1.0
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    out = np.full(len(bars), math.nan)
    for t in range(len(bars)):
        legs = _legs(episode, t)
        kp = int(idx[t]) - 1
        if legs is None or not (legs[0] <= legs[1] <= t) or kp < 13:
            continue
        out[t] = g * (c[t] - day_open[t]) / atr[kp]
    return out


def test_values_weight_and_veto_match_the_research_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    expected = {side: _research(capture, side) for side in ("long", "short")}
    for side in ("long", "short"):
        trace = _mask(capture, side).trace["child:d1:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected[side]).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected[side], rtol=1e-9, atol=1e-12, equal_nan=True)
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    low, high = (
        float((finite[i] + finite[i + 1]) / 2)
        for i in (int(0.1 * len(finite)), int(0.4 * len(finite)))
    )
    for threshold, level in ((0.3, high), (0.9, low)):
        # 0.3: the weight step alone blocks; 0.9: only the veto step blocks.
        recorder, context = _run([_variant("vote", _spec(_vote(high, low, threshold)))])
        assert context.stats.unforeseen_consumptions == 0
        for side in ("long", "short"):
            value = expected[side]
            blocked = np.isfinite(value) & (value <= level)
            assert blocked.any()
            allowed = _mask(recorder.captures[0], side).local_setup_allowed
            assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_operand() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(-0.2 - 0.1 * i, -1.5))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.forming_candle") == 2  # one per side


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.forming_candle") == 0
