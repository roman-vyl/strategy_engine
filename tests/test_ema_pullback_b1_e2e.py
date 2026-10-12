"""B1 end to end (OpenSpec `b1-candle-ratio-v1`, tasks 2.4, 3.1, 3.2): the pullback-over-impulse
candle ratio as `range(ratio(candle, candle))` through the strategy pipeline on the BTCUSDT.P 5m
fixture against a loop written like the research reference, three timeframes, band masks, shared
nodes and a spec without a candle."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_candles import _reference
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)
from strategy_engine.strategies.live_calculation.indicator_requirements import (
    ResolveIndicatorHistoryRequirements,
)

Spec = dict[str, Any]

WINDOW = 12
PERIOD = 14
TIMEFRAMES = ["5m", "15m", "1h"]


def _candle(timeframe: str, leg: str, direction: str) -> Spec:
    return {
        "candle": {
            "episode": "trend",
            "leg": leg,
            "timeframe": timeframe,
            "direction": direction,
            "atr": {"kind": "atr_wilder", "timeframe": timeframe, "params": {"period": PERIOD}},
        }
    }


def _branch(timeframe: str, low: float | None, high: float | None) -> Spec:
    return {
        "kind": "range",
        "operand": {
            "ratio": {
                "left": _candle(timeframe, "pullback", "against"),
                "right": _candle(timeframe, "impulse", "with"),
            }
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
            "instance_id": "b1_branch",
            "params": {
                "children": [{"child_id": "b1", "predicate": branch}],
                "paths": [{"path_id": "pass", "require": ["b1"]}],
            },
        }
    ]
    return spec


def _setup(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _expected(capture: Any, side: str, timeframe: str) -> np.ndarray:
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    bars = capture.frame.market_bars
    time_ms = np.array([b.open_time_ms for b in bars], dtype=np.int64)
    arrays = tuple(
        np.array([float(getattr(b, name)) for b in bars])
        for name in ("open", "high", "low", "close")
    )
    tf_ms = timeframe_duration_ms(timeframe)
    args = (episode, time_ms, arrays, tf_ms)
    pullback = _reference(*args, "pullback", "against", side, True, PERIOD)
    impulse = _reference(*args, "impulse", "with", side, True, PERIOD)
    out = np.full(len(time_ms), math.nan)
    ok = np.isfinite(pullback) & np.isfinite(impulse) & (impulse > 0)
    out[ok] = pullback[ok] / impulse[ok]
    return out


@pytest.mark.parametrize("timeframe", TIMEFRAMES)
def test_value_and_band_masks_match_the_research_loop(timeframe: str) -> None:
    recorder, context = _run([_variant("probe", _spec(_branch(timeframe, None, None)))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _setup(capture, side)
        expected = _expected(capture, side, timeframe)
        values = np.array(
            [math.nan if v is None else v for v in mask.trace["child:b1:value"]], dtype=float
        )
        assert np.isfinite(expected).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-9, atol=1e-12, equal_nan=True)
        assert all(mask.trace["child:b1"])  # no bounds pass everything
        finite = expected[np.isfinite(expected)]
        distinct = np.unique(finite)
        pick = int(0.7 * len(distinct))
        high = float((distinct[pick] + distinct[pick + 1]) / 2)  # never on a value
        banded, _ = _run([_variant("band", _spec(_branch(timeframe, None, high)))])
        got = list(_setup(banded.captures[0], side).trace["child:b1"])
        blocked = np.isfinite(expected) & (expected >= high)
        assert got == list((~blocked).tolist())
        assert blocked.any()


def test_candidates_differing_only_in_the_bound_share_the_operands() -> None:
    variants = [_variant(f"c{i}", _spec(_branch("15m", None, 1.0 + 0.5 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.candle") == 4  # impulse and pullback, per side
    assert _calls(context, "predicate.ratio") == 2
    assert _calls(context, "predicate.range") == 4 * 2


def test_static_validation_and_live_history() -> None:
    spec = _spec(_branch("1h", None, 1.5))
    check_ema_pullback_static_semantics(spec)
    undeclared = copy.deepcopy(spec)
    undeclared["ema_stack_episode"] = {}
    with pytest.raises(Exception, match="not declared"):
        check_ema_pullback_static_semantics(undeclared)
    requirements = EmaPullbackLiveCalculationRequirements().execute(spec)
    predicate_entries = [item for item in requirements if "predicate" in item.reason]
    assert all(item.bars == 0 for item in predicate_entries)
    feature = plan_feature_request("atr_wilder", "1h", None, {"period": PERIOD})
    (need,) = ResolveIndicatorHistoryRequirements().execute(IndicatorPlan("1", (feature,)))
    assert need.timeframe == "1h" and need.bars > 2 * PERIOD


def test_a_spec_without_a_candle_adds_no_candle_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.candle") == 0
