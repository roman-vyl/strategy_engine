"""A1 band filter end to end (OpenSpec `a1-band-filter-v1`, tasks 3.1, 4.1): a `composite_setup`
child `range(ratio(segment, segment))` through the strategy pipeline on the real BTCUSDT.P 5m
fixture, against a research-style per-entry loop, the value trace and memo reuse across band
candidates."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

WINDOW = 12
LAST_N = 20
EMA_FAST = {"kind": "ema", "params": {"period": 5}}
EMA_ANCHOR = {"kind": "ema", "params": {"period": 200}}


def _a1(low: float | None, high: float | None, last_n: int | None = LAST_N) -> Spec:
    series = {"difference": {"left": EMA_FAST, "right": EMA_ANCHOR}}
    window = None if last_n is None else {"last_n": last_n}

    def leg(start: str, end: str, negate: bool) -> Spec:
        return {
            "segment": {
                "episode": "trend",
                "of": series,
                "from": start,
                "to": end,
                "value": "change",
                "window": window,
                "aggregate": "mean_per_bar",
                "negate": negate,
            }
        }

    return {
        "kind": "range",
        "operand": {
            "ratio": {
                "left": leg("peak", "current", True),
                "right": leg("origin", "peak", False),
            }
        },
        "min": low,
        "max": high,
        "bounds": "exclusive",
        "empty": "pass",
    }


def _spec(low: float | None, high: float | None, last_n: int | None = LAST_N) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    spec["setups"] = [
        {
            "component_id": "composite_setup",
            "instance_id": "a1_band",
            "params": {
                "children": [{"child_id": "a1", "predicate": _a1(low, high, last_n)}],
                "paths": [{"path_id": "pass", "require": ["a1"]}],
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


def _reference(capture: Any, side: str, last_n: int | None) -> np.ndarray:
    """A1 per bar like the research loop: d = EMA5 - anchor, delta over the last N bars of each
    leg of the current touch, mean per bar, pullback over impulse."""

    plan = capture.plan
    spec_features = {f.output_id: f for f in plan.indicator_plan.features}
    fast = next(
        k for k, f in spec_features.items() if f.kind == "ema" and f.parameters["period"] == 5
    )
    anchor = next(
        k for k, f in spec_features.items() if f.kind == "ema" and f.parameters["period"] == 200
    )
    d = _series(capture, fast) - _series(capture, anchor)
    if side == "short":
        d = -d
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    state, touches = episode.state, episode.touches
    out = np.full(len(d), math.nan)
    for t in range(len(d)):
        number = state["touch_number"][t]
        if not math.isfinite(number) or number < 1:
            continue
        row = int(episode.first_row[int(state["episode_id"][t])]) + int(number) - 1
        origin, peak = int(touches["origin_bar"][row]), int(touches["peak_bar"][row])

        def mean_delta(start: int, end: int) -> float:
            s = start if last_n is None else max(start, end - last_n + 1)
            if s < 1:
                return math.nan
            return float(np.mean(np.diff(d[s - 1 : end + 1])))

        pullback, impulse = -mean_delta(peak, t), mean_delta(origin, peak)
        if math.isfinite(pullback) and math.isfinite(impulse) and impulse > 0:
            out[t] = pullback / impulse
    return out


@pytest.mark.parametrize("last_n", [LAST_N, None])
def test_a1_value_and_band_masks_match_the_reference(last_n: int | None) -> None:
    recorder, context = _run([_variant("probe", _spec(None, None, last_n))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _setup(capture, side)
        expected = _reference(capture, side, last_n)
        values = np.array(
            [math.nan if v is None else v for v in mask.trace["child:a1:value"]], dtype=float
        )
        assert np.isfinite(expected).sum() > 50, "fixture must give A1 values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-9, equal_nan=True)
        # both sliders off passes everything, including bars without a value
        assert all(mask.trace["child:a1"])
        finite = expected[np.isfinite(expected)]
        low, high = (float(q) for q in np.quantile(finite, [0.3, 0.9]))
        for band in ((low, None), (None, high), (low, high)):
            banded, _ = _run([_variant("band", _spec(band[0], band[1], last_n))])
            (band_capture,) = banded.captures
            got = list(_setup(band_capture, side).trace["child:a1"])
            blocked = np.zeros(len(expected), dtype=bool)
            if band[0] is not None:
                blocked |= np.isfinite(expected) & (expected <= band[0])
            if band[1] is not None:
                blocked |= np.isfinite(expected) & (expected >= band[1])
            assert got == list((~blocked).tolist())
            assert blocked.any()


def test_band_candidates_share_columns_segments_and_ratio() -> None:
    variants = [_variant(f"c{i}", _spec(0.2 + 0.1 * i, None)) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    # two segments and one ratio per side, computed once for the whole batch
    assert _calls(context, "predicate.segment") == 4
    assert _calls(context, "predicate.ratio") == 2
    assert _calls(context, "predicate.range") == 4 * 2
    assert _calls(context, "episode.ema_stack") == 2


def test_static_validation_and_live_history() -> None:
    spec = _spec(0.9, 10)
    check_ema_pullback_static_semantics(spec)
    undeclared = copy.deepcopy(spec)
    undeclared["ema_stack_episode"] = {}
    with pytest.raises(Exception, match="not declared"):
        check_ema_pullback_static_semantics(undeclared)
    requirements = EmaPullbackLiveCalculationRequirements().execute(spec)
    assert any(item.reason.startswith("ema_stack_episode.") for item in requirements)
