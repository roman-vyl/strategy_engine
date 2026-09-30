"""`state` and `temporal` predicates (OpenSpec
`composite-setup-pre-entry-predicates-v1`, group 5): spec scenarios, side
mapping through the existing HTF regime resolution, a mixed
5m/15m/1h/4h composite on real fixture data against a naive per-bar
reference, memo parity and live history."""

from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.predicates import _window_mask
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]


def _context(timeframe: str) -> dict[str, Any]:
    return {
        "component_id": "htf_context",
        "timeframe": timeframe,
        "source": "close",
        "fast_period": 20,
        "anchor_period": 50,
        "slow_period": 100,
    }


CONTEXTS = {"htf_1h": _context("1h"), "htf_4h": _context("4h")}


def _feature(kind: str, period: int, timeframe: str) -> dict[str, Any]:
    return {"feature": {"kind": kind, "timeframe": timeframe, "params": {"period": period}}}


STATE_1H = {"kind": "state", "context_ref": "htf_1h", "in": ["aligned"]}
HELD_1H = {"kind": "temporal", "mode": "held_for", "bars": 36, "of": STATE_1H}
STATE_4H = {"kind": "state", "context_ref": "htf_4h", "in": ["aligned", "neutral"]}
ADX_1H = {"kind": "compare", "left": _feature("adx", 14, "1h"), "op": ">=", "right": {"const": 20}}
RSI_15M = {"kind": "range", "operand": _feature("rsi", 14, "15m"), "min": 35, "max": 70}
CROSS_4H = {
    "kind": "temporal",
    "mode": "within",
    "bars": 12,
    "of": {"kind": "compare", "left": {"price": "close"}, "op": ">",
           "right": _feature("ema", 50, "4h"), "short": {"op": "<"}},
}
PREDICATES = {
    "held1h": HELD_1H,
    "state4h": STATE_4H,
    "adx1h": ADX_1H,
    "rsi15m": RSI_15M,
    "cross4h": CROSS_4H,
}


def _composite(predicates: dict[str, Any] | None = None, instance_id: str = "mixed") -> Spec:
    chosen = PREDICATES if predicates is None else predicates
    ids = list(chosen)
    return {
        "component_id": "composite_setup",
        "instance_id": instance_id,
        "params": {
            "children": [
                {"child_id": child_id, "predicate": copy.deepcopy(predicate)}
                for child_id, predicate in chosen.items()
            ],
            "paths": [
                {"path_id": "strict", "require": ids},
                {"path_id": "loose", "require": ids[:1], "at_least": {"k": 1, "of": ids}},
            ],
        },
    }


def _spec(*setups: Spec) -> Spec:
    spec = base_spec()
    spec["contexts"] = copy.deepcopy(CONTEXTS)
    spec["setups"] = list(setups)
    return spec


def _run(variants: list[dict[str, Any]], *, memo_enabled: bool = True) -> tuple[Recorder, Any]:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(
        recorder, memo_enabled=memo_enabled
    ) as services:
        ndjson = _drain_route(services, batch_payload(variants))
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    for capture in recorder.captures:
        assert capture.exception is None, capture.exception
    return recorder, contexts[0]


def _mask(capture: Any, instance_id: str, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    return next(item for item in side_eval.setups if item.instance_id == instance_id)


def _calls(context: Any, kind: str) -> int:
    return sum(
        count for identity, count in context.stats.compute_calls.items() if identity.kind == kind
    )


# -- temporal spec scenarios (task 5.3) ------------------------------------------


def _bools(true_bars: range, length: int = 30) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    mask[list(true_bars)] = True
    return mask


def test_held_for_n_bars() -> None:
    held = _window_mask("held_for", 5, _bools(range(10, 20)))
    assert not held[10:14].any()
    assert held[14:20].all()
    assert not held[20:].any()


def test_occurred_within_n_bars() -> None:
    within = _window_mask("within", 5, _bools(range(10, 11)))
    assert within[10:15].all()
    assert not within[15]
    assert not within[:10].any()


def test_held_for_at_the_start_of_history() -> None:
    assert not _window_mask("held_for", 5, _bools(range(0, 3))).any()
    # `within` uses the shortened initial window.
    assert _window_mask("within", 5, _bools(range(0, 1)))[:5].all()


@pytest.mark.parametrize("mode", ["held_for", "within"])
def test_one_bar_window_equals_the_inner_predicate(mode: str) -> None:
    inner = np.random.default_rng(7).random(200) > 0.5
    assert (_window_mask(mode, 1, inner) == inner).all()


@pytest.mark.parametrize("bars", [1, 2, 7, 36, 250])
def test_windows_match_a_naive_reference(bars: int) -> None:
    inner = np.random.default_rng(bars).random(400) > 0.3
    held = [i >= bars - 1 and bool(inner[i - bars + 1 : i + 1].all()) for i in range(400)]
    within = [bool(inner[max(0, i - bars + 1) : i + 1].any()) for i in range(400)]
    assert _window_mask("held_for", bars, inner).tolist() == held
    assert _window_mask("within", bars, inner).tolist() == within


# -- static validation (tasks 1.2, 5.x) ------------------------------------------


def test_mixed_composite_is_valid() -> None:
    check_ema_pullback_static_semantics(_spec(_composite()))


@pytest.mark.parametrize(
    "predicate",
    [
        pytest.param({**STATE_1H, "context_ref": "missing"}, id="undeclared-context"),
        pytest.param({**STATE_1H, "in": []}, id="empty-in"),
        pytest.param({**STATE_1H, "in": ["up"]}, id="raw-state-in"),
        pytest.param({**STATE_1H, "in": ["aligned", "aligned"]}, id="duplicate-in"),
        pytest.param({**STATE_1H, "short": {"in": ["countertrend"]}}, id="state-short"),
        pytest.param({**HELD_1H, "bars": 0}, id="zero-bars"),
        pytest.param({**HELD_1H, "bars": True}, id="bool-bars"),
        pytest.param({**HELD_1H, "mode": "for_each"}, id="unknown-mode"),
        pytest.param({**HELD_1H, "of": HELD_1H}, id="temporal-of-temporal"),
        pytest.param({**HELD_1H, "of": {**STATE_1H, "context_ref": "x"}}, id="inner-undeclared"),
        pytest.param({**HELD_1H, "short": {"bars": 3}}, id="temporal-short"),
    ],
)
def test_invalid_state_or_temporal_is_rejected(predicate: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec(_composite({"p": predicate})))


# -- real fixture data (tasks 5.2, 5.6) ------------------------------------------

_REGIME = {
    "long": {"up": "aligned", "down": "countertrend", "neutral": "neutral"},
    "short": {"up": "countertrend", "down": "aligned", "neutral": "neutral"},
}


def _naive(predicate: dict[str, Any], side: str, capture: Any) -> list[bool]:
    frame = capture.frame
    length = len(frame.time_ms)
    kind = predicate["kind"]
    if kind == "temporal":
        inner = _naive(predicate["of"], side, capture)
        bars = predicate["bars"]
        if predicate["mode"] == "held_for":
            return [i >= bars - 1 and all(inner[i - bars + 1 : i + 1]) for i in range(length)]
        return [any(inner[max(0, i - bars + 1) : i + 1]) for i in range(length)]
    if kind == "state":
        output = next(
            item
            for item in capture.evaluation.contexts.outputs
            if item.context_ref == predicate["context_ref"]
        )
        return [_REGIME[side][state] in predicate["in"] for state in output.state]
    effective = dict(predicate)
    if side == "short" and "short" in predicate:
        effective.update(predicate["short"])

    def value(operand: dict[str, Any], bar: int) -> float:
        if "const" in operand:
            return float(operand["const"])
        if "price" in operand:
            return float(getattr(frame.market_bars[bar], operand["price"]))
        feature = operand["feature"]
        label = f"{feature['kind']}_close_{feature['timeframe']}_{feature['params']['period']}"
        raw = frame.series[label][bar]
        return math.nan if raw is None else float(raw)

    out: list[bool] = []
    for bar in range(length):
        if kind == "compare":
            left, right = value(effective["left"], bar), value(effective["right"], bar)
            ok = {
                ">": left > right,
                ">=": left >= right,
                "<": left < right,
                "<=": left <= right,
            }[effective["op"]]
            out.append(math.isfinite(left) and math.isfinite(right) and ok)
        else:
            v = value(effective["operand"], bar)
            out.append(math.isfinite(v) and effective["min"] <= v <= effective["max"])
    return out


def test_mixed_timeframe_composite_matches_a_naive_reference() -> None:
    recorder, context = _run([_variant("mixed", _spec(_composite()))])
    capture = recorder.captures[0]
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _mask(capture, "mixed", side)
        children = {}
        for child_id, predicate in PREDICATES.items():
            expected = _naive(predicate, side, capture)
            assert list(mask.trace[f"child:{child_id}"]) == expected, (side, child_id)
            assert any(expected) and not all(expected), (side, child_id)
            children[child_id] = expected
        strict = [all(values) for values in zip(*children.values(), strict=True)]
        assert list(mask.trace["path:strict"]) == strict


def test_state_maps_aligned_to_up_for_long_and_down_for_short() -> None:
    recorder, _ = _run([_variant("state", _spec(_composite({"s": STATE_1H})))])
    capture = recorder.captures[0]
    output = next(o for o in capture.evaluation.contexts.outputs if o.context_ref == "htf_1h")
    assert _mask(capture, "mixed", "long").trace["child:s"] == output.up
    assert _mask(capture, "mixed", "short").trace["child:s"] == output.down


def test_side_free_inner_is_shared_and_state_is_per_side() -> None:
    within = {
        "kind": "temporal",
        "mode": "within",
        "bars": 6,
        "of": {"kind": "compare", "left": _feature("adx", 14, "1h"), "op": ">",
               "right": {"const": 20}},
    }
    _, context = _run([_variant("x", _spec(_composite({"w": within, "s": STATE_1H})))])
    assert _calls(context, "predicate.compare") == 1
    assert _calls(context, "predicate.temporal") == 1
    assert _calls(context, "predicate.state") == 2


def test_memo_on_and_off_are_identical() -> None:
    swept = {**PREDICATES, "held1h": {**HELD_1H, "bars": 12}}
    variants = [
        _variant("a", _spec(_composite())),
        _variant("b", _spec(_composite(swept))),
        _variant("c", _spec(_composite(instance_id="other"))),
    ]
    on, context = _run(variants, memo_enabled=True)
    off, _ = _run(variants, memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.state") == 4  # 1h and 4h, per side, shared by a/b/c
    for left, right in zip(on.captures, off.captures, strict=True):
        for left_side, right_side in zip(
            left.evaluation.setups, right.evaluation.setups, strict=True
        ):
            assert left_side.setups_ok == right_side.setups_ok
            for left_mask, right_mask in zip(left_side.setups, right_side.setups, strict=True):
                assert left_mask.final_setup_allowed == right_mask.final_setup_allowed
                assert left_mask.trace == right_mask.trace
        assert left.evaluation.entries == right.evaluation.entries


# -- live history (task 5.5) -----------------------------------------------------


def test_live_history_of_temporal_predicates() -> None:
    requirements = EmaPullbackLiveCalculationRequirements().execute(_spec(_composite()))
    by_child = {
        item.reason.split(" ")[0]: item.bars for item in requirements if "predicate" in item.reason
    }
    assert by_child == {
        "setups[0].held1h": 35,
        "setups[0].state4h": 0,
        "setups[0].adx1h": 0,
        "setups[0].rsi15m": 0,
        "setups[0].cross4h": 11,
    }
