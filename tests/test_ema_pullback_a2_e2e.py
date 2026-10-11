"""A2 branches end to end (OpenSpec `a2-shape-aggregates-v1`, tasks 2.4, 2.5, 3.1, 3.2): each
branch as `range(ratio(segment, segment))` through the strategy pipeline on the BTCUSDT.P 5m
fixture against a loop written like the research reference, a second anchor period, band masks
and memo reuse."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_predicates_a2 import _research
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

WINDOW = 12
LEG_WINDOW = 20
SHORT = 5
SPAN = 3
TOP = 5
ACCEL_MIN = 8
CONC_MIN = 8
EMA_FAST = {"kind": "ema", "params": {"period": 5}}


def _anchor(period: int) -> Spec:
    return {"kind": "ema", "params": {"period": period}}


def _branch(name: str, low: float | None, high: float | None, anchor_period: int = 200) -> Spec:
    series = {"difference": {"left": EMA_FAST, "right": _anchor(anchor_period)}}
    eligibility = {"legs_min_bars": 3, "window": LEG_WINDOW, "impulse_positive": True}
    if name == "accel":
        eligibility = {**eligibility, "pullback_min_bars": ACCEL_MIN}
    elif name == "conc":
        eligibility = {**eligibility, "pullback_min_bars": CONC_MIN}

    def seg(start: str, end: str, window: int, **fields: Any) -> Spec:
        return {
            "segment": {
                "episode": "trend",
                "of": series,
                "from": start,
                "to": end,
                "window": {"last_n": window},
                "eligibility": eligibility,
                **fields,
            }
        }

    if name == "accel":
        operand = {
            "left": seg(
                "peak", "current", SHORT, value="change", aggregate="mean_per_bar", negate=True
            ),
            "right": seg(
                "peak", "current", LEG_WINDOW, value="change", aggregate="mean_per_bar", negate=True
            ),
        }
    elif name == "peak":
        operand = {
            "left": seg(
                "peak",
                "current",
                LEG_WINDOW,
                value="change_over",
                span=SPAN,
                aggregate="min",
                negate=True,
            ),
            "right": seg(
                "origin", "peak", LEG_WINDOW, value="change_over", span=SPAN, aggregate="max"
            ),
        }
    else:
        operand = seg(
            "peak", "current", LEG_WINDOW, value="change", aggregate="top_abs_share", top=TOP
        )
    return {
        "kind": "range",
        "operand": {"ratio": operand} if name != "conc" else operand,
        "min": low,
        "max": high,
        "bounds": "exclusive",
        "empty": "pass",
    }


def _spec(branch: Spec) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    spec["setups"] = [
        {
            "component_id": "composite_setup",
            "instance_id": "a2_branch",
            "params": {
                "children": [{"child_id": "a2", "predicate": branch}],
                "paths": [{"path_id": "pass", "require": ["a2"]}],
            },
        }
    ]
    return spec


def _setup(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _series(capture: Any, label: str) -> np.ndarray:
    return np.array(
        [math.nan if v is None else float(v) for v in capture.frame.series[label]], dtype=float
    )


def _line(capture: Any, side: str, anchor_period: int) -> np.ndarray:
    features = {f.output_id: f for f in capture.plan.indicator_plan.features}

    def column(period: int) -> str:
        return next(
            k for k, f in features.items() if f.kind == "ema" and f.parameters["period"] == period
        )

    d = _series(capture, column(5)) - _series(capture, column(anchor_period))
    return -d if side == "short" else d


@pytest.mark.parametrize("anchor_period", [200, 100])
@pytest.mark.parametrize("name", ["accel", "peak", "conc"])
def test_branch_value_and_band_masks_match_the_research_loop(name: str, anchor_period: int) -> None:
    recorder, context = _run([_variant("probe", _spec(_branch(name, None, None, anchor_period)))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _setup(capture, side)
        episode = capture.evaluation.contexts.episodes.side("trend", side)
        expected = _research(
            episode,
            _line(capture, side, anchor_period),
            window=LEG_WINDOW,
            short=SHORT,
            k=SPAN,
            top=TOP,
            accel_min=ACCEL_MIN,
            conc_min=CONC_MIN,
        )[name]
        values = np.array(
            [math.nan if v is None else v for v in mask.trace["child:a2:value"]], dtype=float
        )
        assert np.isfinite(expected).sum() > 30, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-12, equal_nan=True)
        assert all(mask.trace["child:a2"])  # both sliders off pass everything
        finite = expected[np.isfinite(expected)]
        low, high = (float(q) for q in np.quantile(finite, [0.3, 0.9]))
        for band in ((low, None), (None, high), (low, high)):
            banded, _ = _run([_variant("band", _spec(_branch(name, *band, anchor_period)))])
            (band_capture,) = banded.captures
            got = list(_setup(band_capture, side).trace["child:a2"])
            blocked = np.zeros(len(expected), dtype=bool)
            if band[0] is not None:
                blocked |= np.isfinite(expected) & (expected <= band[0])
            if band[1] is not None:
                blocked |= np.isfinite(expected) & (expected >= band[1])
            assert got == list((~blocked).tolist())
            assert blocked.any()


def test_branch_candidates_share_columns_segments_and_ratio() -> None:
    variants = [_variant(f"c{i}", _spec(_branch("peak", 0.2 + 0.1 * i, None))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    # two segments and one ratio per side, computed once for the whole batch
    assert _calls(context, "predicate.segment") == 4
    assert _calls(context, "predicate.ratio") == 2
    assert _calls(context, "predicate.range") == 4 * 2


def test_branches_with_the_same_eligibility_share_the_episode() -> None:
    variants = [
        _variant(name, _spec(_branch(name, 0.3, None))) for name in ("accel", "peak", "conc")
    ]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 3
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "episode.ema_stack") == 2


def test_static_validation_and_live_history_are_zero_additional() -> None:
    spec = _spec(_branch("peak", 0.3, None))
    check_ema_pullback_static_semantics(spec)
    undeclared = copy.deepcopy(spec)
    undeclared["ema_stack_episode"] = {}
    with pytest.raises(Exception, match="not declared"):
        check_ema_pullback_static_semantics(undeclared)
    requirements = EmaPullbackLiveCalculationRequirements().execute(spec)
    predicate_entries = [item for item in requirements if "predicate" in item.reason]
    assert all(item.bars == 0 for item in predicate_entries)
    assert any(item.reason.startswith("ema_stack_episode.") for item in requirements)


@pytest.mark.parametrize("name", ["accel", "peak", "conc"])
def test_memoized_and_plain_evaluation_agree(name: str) -> None:
    spec = _spec(_branch(name, 0.3, None))
    on, context = _run([_variant("a2", spec)], memo_enabled=True)
    off, _ = _run([_variant("a2", spec)], memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        assert _setup(on.captures[0], side).trace == _setup(off.captures[0], side).trace
    assert on.captures[0].projection == off.captures[0].projection
