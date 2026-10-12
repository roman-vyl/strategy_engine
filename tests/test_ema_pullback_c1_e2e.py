"""C1.1 and C1.2 end to end (OpenSpec `c1-di-pullback-wave-v1`, tasks 2.3, 3.1, 3.2): each as
`range(ratio(segment, segment))` through the strategy pipeline on the BTCUSDT.P 5m fixture against
a loop written like the research reference, two DI periods, band masks and memo reuse."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_predicates_c1 import _reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

WINDOW = 12
FLOOR = 1e-6
AGGREGATE = {"c11": "max", "c12": "mean_per_bar"}
KEY = {"c11": "rise", "c12": "area"}


def _branch(name: str, low: float | None, high: float | None, period: int = 14) -> Spec:
    series = {
        "by_side": {
            "long": {"kind": "di_minus", "params": {"period": period}},
            "short": {"kind": "di_plus", "params": {"period": period}},
        }
    }

    def seg(touch: str) -> Spec:
        return {
            "segment": {
                "episode": "trend",
                "of": series,
                "from": "peak",
                "to": "current" if touch == "current" else "touch",
                "value": "from_start",
                "aggregate": AGGREGATE[name],
                "touch": touch,
            }
        }

    return {
        "kind": "range",
        "operand": {
            "ratio": {"left": seg("current"), "right": seg("previous"), "right_floor": FLOOR}
        },
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
            "instance_id": "c1_branch",
            "params": {
                "children": [{"child_id": "c1", "predicate": branch}],
                "paths": [{"path_id": "pass", "require": ["c1"]}],
            },
        }
    ]
    return spec


def _setup(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _line(capture: Any, side: str, period: int) -> np.ndarray:
    kind = "di_minus" if side == "long" else "di_plus"
    label = next(
        k
        for k, f in {f.output_id: f for f in capture.plan.indicator_plan.features}.items()
        if f.kind == kind and f.parameters["period"] == period
    )
    return np.array(
        [math.nan if v is None else float(v) for v in capture.frame.series[label]], dtype=float
    )


def _expected(capture: Any, side: str, name: str, period: int) -> np.ndarray:
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    line = _line(capture, side, period)
    ref = _reference(episode, line)
    now, before = ref[KEY[name]], ref["prev_" + KEY[name]]
    out = np.full(len(line), math.nan)
    ok = np.isfinite(now) & np.isfinite(before) & (before > FLOOR)
    out[ok] = now[ok] / before[ok]
    return out


@pytest.mark.parametrize("period", [14, 28])
@pytest.mark.parametrize("name", ["c11", "c12"])
def test_branch_value_and_band_masks_match_the_research_loop(name: str, period: int) -> None:
    recorder, context = _run([_variant("probe", _spec(_branch(name, None, None, period)))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _setup(capture, side)
        expected = _expected(capture, side, name, period)
        values = np.array(
            [math.nan if v is None else v for v in mask.trace["child:c1:value"]], dtype=float
        )
        assert np.isfinite(expected).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-9, equal_nan=True)
        assert all(mask.trace["child:c1"])  # no bounds pass everything
        finite = expected[np.isfinite(expected)]
        distinct = np.unique(finite)
        pick = int(0.3 * len(distinct))
        low = float((distinct[pick] + distinct[pick + 1]) / 2)  # never on a value
        banded, _ = _run([_variant("band", _spec(_branch(name, low, None, period)))])
        got = list(_setup(banded.captures[0], side).trace["child:c1"])
        blocked = np.isfinite(expected) & (expected <= low)
        assert got == list((~blocked).tolist())
        assert blocked.any()


def test_candidates_differing_only_in_the_bound_share_segments_and_ratio() -> None:
    variants = [_variant(f"c{i}", _spec(_branch("c11", 0.2 + 0.1 * i, None))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.segment") == 4  # current and previous, per side
    assert _calls(context, "predicate.ratio") == 2
    assert _calls(context, "predicate.range") == 4 * 2


def test_c11_and_c12_share_the_di_columns() -> None:
    variants = [_variant(name, _spec(_branch(name, 0.5, None))) for name in ("c11", "c12")]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 2
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.column") == 2
    assert _calls(context, "episode.ema_stack") == 2


def test_static_validation_and_live_history() -> None:
    spec = _spec(_branch("c11", 0.5, None))
    check_ema_pullback_static_semantics(spec)
    undeclared = copy.deepcopy(spec)
    undeclared["ema_stack_episode"] = {}
    with pytest.raises(Exception, match="not declared"):
        check_ema_pullback_static_semantics(undeclared)
    requirements = EmaPullbackLiveCalculationRequirements().execute(spec)
    predicate_entries = [item for item in requirements if "predicate" in item.reason]
    assert all(item.bars == 0 for item in predicate_entries)


@pytest.mark.parametrize("name", ["c11", "c12"])
def test_memoized_and_plain_evaluation_agree(name: str) -> None:
    spec = _spec(_branch(name, 0.5, None))
    on, context = _run([_variant("c1", spec)], memo_enabled=True)
    off, _ = _run([_variant("c1", spec)], memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        assert _setup(on.captures[0], side).trace == _setup(off.captures[0], side).trace
    assert on.captures[0].projection == off.captures[0].projection
