"""Owner example end-to-end through `/range-batch` (OpenSpec
`composite-setup-pre-entry-predicates-v1`, task 6.1): the two-path spec
from design D1 (HTF held, ADX 1h/5m, RSI, `at_least`) on real BTCUSDT.P 5m
fixture data. Final masks and `winning_path` are checked against a naive
per-bar reference; semantic setup children against the same setups
evaluated as plain top-level setups in the same batch."""

from __future__ import annotations

import copy
import math
from typing import Any

from parity.corpus import _variant, _width, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts

Spec = dict[str, Any]


def _feature(kind: str, timeframe: str, period: int = 14) -> dict[str, Any]:
    return {"feature": {"kind": kind, "timeframe": timeframe, "params": {"period": period}}}


def _setup_child(child_id: str, setup: Spec) -> Spec:
    return {
        "child_id": child_id,
        "setup": {"component_id": setup["component_id"], "params": setup["params"]},
    }


WIDTH8 = _width("width8", min_current_width_atr=8)
WIDTH10 = _width("width10", min_current_width_atr=10)

PREDICATES: dict[str, Spec] = {
    "htf1h_held": {
        "kind": "temporal",
        "mode": "held_for",
        "bars": 36,
        "of": {"kind": "state", "context_ref": "htf_1h", "in": ["aligned"]},
    },
    "adx1h_25": {"kind": "compare", "left": _feature("adx", "1h"), "op": ">=",
                 "right": {"const": 25}},
    "rsi5m_lt70": {
        "kind": "compare",
        "left": _feature("rsi", "5m"),
        "op": "<",
        "right": {"const": 70},
        "short": {"op": ">", "right": {"const": 30}},
    },
    "adx1h_20": {"kind": "compare", "left": _feature("adx", "1h"), "op": ">=",
                 "right": {"const": 20}},
    "adx5m_25": {"kind": "compare", "left": _feature("adx", "5m"), "op": ">=",
                 "right": {"const": 25}},
    "rsi_range": {"kind": "range", "operand": _feature("rsi", "5m"), "min": 40, "max": 65},
}

PATHS = [
    {"path_id": "developed", "require": ["width8", "htf1h_held", "adx1h_25", "rsi5m_lt70"]},
    {
        "path_id": "alternate",
        "require": ["width10"],
        "at_least": {"k": 2, "of": ["adx1h_20", "adx5m_25", "rsi_range"]},
    },
]

CONTEXTS = {
    "htf_1h": {
        "component_id": "htf_context",
        "timeframe": "1h",
        "source": "close",
        "fast_period": 20,
        "anchor_period": 50,
        "slow_period": 100,
    }
}


def _spec(setups: list[Spec]) -> Spec:
    spec = base_spec()
    spec["contexts"] = copy.deepcopy(CONTEXTS)
    spec["setups"] = setups
    return spec


def _owner_example() -> Spec:
    children = [_setup_child("width8", WIDTH8), _setup_child("width10", WIDTH10)]
    children += [
        {"child_id": child_id, "predicate": copy.deepcopy(predicate)}
        for child_id, predicate in PREDICATES.items()
    ]
    return _spec(
        [
            {
                "component_id": "composite_setup",
                "instance_id": "trend_ready",
                "params": {"children": children, "paths": copy.deepcopy(PATHS)},
            }
        ]
    )


_REGIME = {"long": {"up": "aligned", "down": "countertrend", "neutral": "neutral"},
           "short": {"up": "countertrend", "down": "aligned", "neutral": "neutral"}}
_OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}


def _naive_predicate(predicate: Spec, side: str, capture: Any) -> list[bool]:
    frame = capture.frame
    length = len(frame.time_ms)
    if predicate["kind"] == "temporal":
        inner = _naive_predicate(predicate["of"], side, capture)
        bars = predicate["bars"]
        return [i >= bars - 1 and all(inner[i - bars + 1 : i + 1]) for i in range(length)]
    if predicate["kind"] == "state":
        output = next(o for o in capture.evaluation.contexts.outputs
                      if o.context_ref == predicate["context_ref"])
        return [_REGIME[side][state] in predicate["in"] for state in output.state]
    effective = {**predicate, **(predicate.get("short", {}) if side == "short" else {})}

    def value(operand: Spec, bar: int) -> float:
        if "const" in operand:
            return float(operand["const"])
        feature = operand["feature"]
        label = f"{feature['kind']}_close_{feature['timeframe']}_{feature['params']['period']}"
        raw = frame.series[label][bar]
        return math.nan if raw is None else float(raw)

    out = []
    for bar in range(length):
        if effective["kind"] == "compare":
            left, right = value(effective["left"], bar), value(effective["right"], bar)
            out.append(math.isfinite(left) and math.isfinite(right)
                       and _OPS[effective["op"]](left, right))
        else:
            v = value(effective["operand"], bar)
            out.append(math.isfinite(v) and effective["min"] <= v <= effective["max"])
    return out


def _side(capture: Any, side: str) -> Any:
    return next(item for item in capture.evaluation.setups if item.side == side)


def test_owner_example_end_to_end() -> None:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(recorder) as services:
        ndjson = _drain_route(
            services,
            batch_payload(
                [
                    _variant("owner-example", _owner_example()),
                    _variant("plain-widths", _spec([WIDTH8, WIDTH10])),
                ]
            ),
        )
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    assert len(ndjson["lines"]) == 2
    composite, plain = recorder.captures
    assert composite.exception is None and plain.exception is None
    assert contexts[0].stats.unforeseen_consumptions == 0

    coverage = {"developed": 0, "alternate": 0}
    for side in ("long", "short"):
        plain_masks = {m.instance_id: m.local_setup_allowed for m in _side(plain, side).setups}
        children = {
            "width8": list(plain_masks["width8"]),
            "width10": list(plain_masks["width10"]),
        }
        for child_id, predicate in PREDICATES.items():
            children[child_id] = _naive_predicate(predicate, side, composite)
        length = len(composite.frame.time_ms)
        developed = [all(children[c][i] for c in PATHS[0]["require"]) for i in range(length)]
        alternate = [
            children["width10"][i]
            and sum(children[c][i] for c in PATHS[1]["at_least"]["of"]) >= 2
            for i in range(length)
        ]
        local = [a or b for a, b in zip(developed, alternate, strict=True)]
        winning = ["developed" if d else "alternate" if a else None
                   for d, a in zip(developed, alternate, strict=True)]

        side_eval = _side(composite, side)
        (mask,) = side_eval.setups
        for child_id, expected in children.items():
            assert list(mask.trace[f"child:{child_id}"]) == expected, (side, child_id)
        assert list(mask.trace["path:developed"]) == developed
        assert list(mask.trace["path:alternate"]) == alternate
        assert list(mask.local_setup_allowed) == local
        assert list(mask.final_setup_allowed) == local  # no context gate on the composite
        assert list(mask.trace["winning_path"]) == winning
        assert list(side_eval.setups_ok) == local
        prior = next(p for p in composite.evaluation.direction_blockers if p.side == side)
        assert list(side_eval.pre_trigger_allowed) == [
            a and b for a, b in zip(prior.pre_setup_allowed, local, strict=True)
        ]
        coverage["developed"] += sum(developed)
        coverage["alternate"] += sum(alternate)
    # The fixture exercises both paths.
    assert coverage["developed"] > 0 and coverage["alternate"] > 0, coverage
