"""C5 end to end (OpenSpec `c5-anchor-follow-v1`, tasks 2.4, 2.7, 3.1, 3.2): the
share of the gap to the anchor closed by the EMA as `range(anchor_follow)` through
the strategy pipeline on the BTCUSDT.P 5m fixture, band masks, the anchor of the
stack, shared nodes and a spec without the operand."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

WINDOW = 12


def _branch(low: float | None, high: float | None) -> Spec:
    return {
        "kind": "range",
        "operand": {"anchor_follow": {"episode": "trend"}},
        "min": low,
        "max": high,
        "bounds": "exclusive",
        "empty": "pass",
    }


def _spec(branch: Spec, anchor_period: int | None = None) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    if anchor_period is not None:
        spec["anchor_stack"] = {
            "fast": {"period": anchor_period // 2, "source": "close", "timeframe": "base"},
            "anchor": {"period": anchor_period, "source": "close", "timeframe": "base"},
            "slow": {"period": anchor_period * 3, "source": "close", "timeframe": "base"},
        }
    spec["setups"] = [
        {
            "component_id": "composite_setup",
            "instance_id": "c5_branch",
            "params": {
                "children": [{"child_id": "c5", "predicate": branch}],
                "paths": [{"path_id": "pass", "require": ["c5"]}],
            },
        }
    ]
    return spec


def _setup(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _expected(capture: Any, side: str, anchor: np.ndarray) -> np.ndarray:
    """The research loop: `c5_engine_ref.py` on the frame's own anchor EMA."""

    episode = capture.evaluation.contexts.episodes.side("trend", side)
    g = 1.0 if side == "long" else -1.0
    size = len(anchor)
    out = np.full(size, math.nan)
    state, touches = episode.state, episode.touches
    for t in range(size):
        number = state["touch_number"][t]
        if not np.isfinite(number) or number < 1:
            continue
        row = int(episode.first_row[int(state["episode_id"][t])]) + int(number) - 1
        peak = touches["peak_bar"][row]
        if not np.isfinite(peak) or not peak <= t:
            continue
        peak = int(peak)
        gap = g * (touches["peak_price"][row] - anchor[peak])
        move = g * (anchor[t] - anchor[peak])
        if np.isfinite(gap) and np.isfinite(move) and gap > 0:
            out[t] = move / gap
    return out


def _anchor(capture: Any, period: int) -> np.ndarray:
    return np.asarray(capture.frame.series.get(f"ema_close_base_{period}"), dtype=float)


def test_value_and_band_masks_match_the_research_loop() -> None:
    recorder, context = _run([_variant("probe", _spec(_branch(None, None)))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    anchor = _anchor(capture, 200)
    for side in ("long", "short"):
        mask = _setup(capture, side)
        expected = _expected(capture, side, anchor)
        values = np.array(
            [math.nan if v is None else v for v in mask.trace["child:c5:value"]], dtype=float
        )
        assert np.isfinite(expected).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-12, equal_nan=True)
        assert all(mask.trace["child:c5"])  # no bounds pass everything
        finite = np.unique(expected[np.isfinite(expected)])
        i, j = int(0.2 * len(finite)), int(0.8 * len(finite))
        low = float((finite[i] + finite[i + 1]) / 2)  # never on a value (the edge is unit-tested)
        high = float((finite[j] + finite[j + 1]) / 2)
        banded, _ = _run([_variant("band", _spec(_branch(low, high)))])
        got = list(_setup(banded.captures[0], side).trace["child:c5"])
        blocked = np.isfinite(expected) & ((expected <= low) | (expected >= high))
        assert got == list((~blocked).tolist())
        assert blocked.any()


def test_the_anchor_follows_the_stack() -> None:
    for period in (200, 240):
        recorder, _ = _run([_variant(f"s{period}", _spec(_branch(None, None), period))])
        (capture,) = recorder.captures
        episode = capture.evaluation.contexts.episodes.side("trend", "long")
        np.testing.assert_array_equal(episode.anchor, _anchor(capture, period))


def test_candidates_differing_only_in_the_bound_share_the_operand() -> None:
    variants = [_variant(f"c{i}", _spec(_branch(0.05 * (i + 1), None))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.anchor_follow") == 2  # one per side
    assert _calls(context, "predicate.range") == 4 * 2


def test_static_validation() -> None:
    spec = _spec(_branch(0.55, None))
    check_ema_pullback_static_semantics(spec)
    undeclared = copy.deepcopy(spec)
    undeclared["ema_stack_episode"] = {}
    with pytest.raises(Exception, match="not declared"):
        check_ema_pullback_static_semantics(undeclared)


def test_a_spec_without_the_operand_adds_no_anchor_follow_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.anchor_follow") == 0
