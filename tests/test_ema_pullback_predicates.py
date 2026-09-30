"""Pre-entry predicates `compare`/`range` as composite children (OpenSpec
`composite-setup-pre-entry-predicates-v1`, group 4): validation through the
canonical feature-kind contract, per-bar semantics against a naive
reference on real fixture data, planning/label collision, shared columns,
side overrides, memo parity and live history."""

from __future__ import annotations

import ast
import copy
import math
import operator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from parity.corpus import _RSI_BLOCKER, _untouched, _variant, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts

import strategy_engine.strategies.ema_pullback.predicates as predicates_module
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.feature_kinds import feature_kinds
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.predicates import (
    Compare,
    Operand,
    Predicate,
    Range,
    evaluate_predicate,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]


def _feature(kind: str, period: int, timeframe: str | None = None, **extra: Any) -> dict[str, Any]:
    feature: dict[str, Any] = {"kind": kind, "params": {"period": period}, **extra}
    if timeframe is not None:
        feature["timeframe"] = timeframe
    return {"feature": feature}


ADX_1H = _feature("adx", 14, "1h")
RSI = _feature("rsi", 14)
EMA_1H_100 = _feature("ema", 100, "1h")
EMA_1H_500 = _feature("ema", 500, "1h")

P_ADX = {"kind": "compare", "left": ADX_1H, "op": ">=", "right": {"const": 25}}
P_RSI = {
    "kind": "compare",
    "left": RSI,
    "op": "<",
    "right": {"const": 70},
    "short": {"op": ">", "right": {"const": 30}},
}
P_EMA = {
    "kind": "compare",
    "left": EMA_1H_100,
    "op": ">",
    "right": EMA_1H_500,
    "short": {"op": "<"},
}
P_RANGE = {"kind": "range", "operand": RSI, "min": 40, "max": 65}
P_PRICE = {"kind": "compare", "left": {"price": "close"}, "op": ">", "right": EMA_1H_100}

PREDICATES = {"adx": P_ADX, "rsi": P_RSI, "ema": P_EMA, "rng": P_RANGE, "px": P_PRICE}


def _composite(
    instance_id: str = "combo", predicates: dict[str, Any] | None = None
) -> dict[str, Any]:
    chosen = PREDICATES if predicates is None else predicates
    untouched = _untouched("u")
    children = [
        {"child_id": child_id, "predicate": copy.deepcopy(predicate)}
        for child_id, predicate in chosen.items()
    ]
    children.append(
        {"child_id": "u", "setup": {"component_id": untouched["component_id"],
                                    "params": untouched["params"]}}
    )
    ids = list(chosen)
    return {
        "component_id": "composite_setup",
        "instance_id": instance_id,
        "params": {
            "children": children,
            "paths": [
                {"path_id": "all", "require": ids},
                {"path_id": "some", "at_least": {"k": 2, "of": [*ids, "u"]}},
            ],
        },
    }


def _spec(*setups: dict[str, Any]) -> Spec:
    spec = base_spec()
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


# -- architecture (task 4.1) -----------------------------------------------------


def test_predicate_layer_knows_no_indicator_kinds() -> None:
    source = Path(predicates_module.__file__).read_text()
    tree = ast.parse(source)
    kinds = {contract.kind for contract in feature_kinds()}
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not literals & kinds
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "indicators.implementations" not in (node.module or "")
        if isinstance(node, ast.Import):
            assert all("indicators.implementations" not in alias.name for alias in node.names)


# -- static validation (tasks 1.2, 4.1) ------------------------------------------


def test_owner_like_predicates_are_valid() -> None:
    check_ema_pullback_static_semantics(_spec(_composite()))


def _with_predicate(predicate: dict[str, Any]) -> Spec:
    return _spec(_composite(predicates={"p": predicate}))


@pytest.mark.parametrize(
    "predicate",
    [
        pytest.param({**P_ADX, "op": "=="}, id="equality-op"),
        pytest.param({**P_ADX, "op": "!="}, id="inequality-op"),
        pytest.param({**P_ADX, "side_relative": True}, id="side-relative"),
        pytest.param({**P_ADX, "left": {"const": 1}}, id="two-constants"),
        pytest.param({**P_RANGE, "min": 70}, id="range-min-above-max"),
        pytest.param({**P_RANGE, "operand": {"const": 1}}, id="range-const-operand"),
        pytest.param({**P_RANGE, "short": {"operand": RSI}}, id="range-short-operand"),
        pytest.param({**P_ADX, "short": {}}, id="empty-short"),
        pytest.param({**P_ADX, "right": {"const": math.inf}}, id="non-finite-const"),
        pytest.param({**P_ADX, "left": _feature("bollinger", 20)}, id="unknown-kind"),
        pytest.param(
            {**P_ADX, "left": {"feature": {"kind": "atr_distance", "params": {"multiplier": 2}}}},
            id="non-requestable-kind",
        ),
        pytest.param({**P_ADX, "left": _feature("rsi", 14, source="open")}, id="rsi-open"),
        pytest.param({**P_ADX, "left": _feature("rsi", 0)}, id="rsi-period-0"),
        pytest.param({**P_ADX, "left": _feature("rsi", 14, "1x")}, id="bad-timeframe"),
        pytest.param({**P_ADX, "left": {"price": "hl2"}}, id="unknown-price"),
        pytest.param({**P_ADX, "left": {"price": "close", "const": 1}}, id="two-operand-kinds"),
        pytest.param({"kind": "not", "of": P_ADX}, id="negation"),
        pytest.param(
            {"kind": "state", "context_ref": "htf", "in": ["aligned"]},
            id="state-undeclared-context",
        ),
    ],
)
def test_invalid_predicate_is_rejected(predicate: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_with_predicate(predicate))


def test_predicate_at_top_level_is_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec({**P_ADX, "instance_id": "p"}))


# -- planning (tasks 4.2, 4.3) ---------------------------------------------------


def test_predicate_features_are_planned_after_existing_consumers() -> None:
    plain = build_feature_plan_from_canonical_spec(_spec(_untouched("u")))
    planned = build_feature_plan_from_canonical_spec(_spec(_composite()))
    plain_labels = [f.output_id for f in plain.indicator_plan.features]
    labels = [f.output_id for f in planned.indicator_plan.features]
    assert labels[: len(plain_labels)] == plain_labels
    assert labels[len(plain_labels) :] == [
        "adx_close_1h_14",
        "rsi_close_base_14",
        "ema_close_1h_100",
        "ema_close_1h_500",
    ]


def test_ema_source_collision_fails_closed() -> None:
    # The stack anchor already owns `ema_close_base_200` with source close.
    predicate = {**P_ADX, "left": _feature("ema", 200, source="open")}
    with pytest.raises(InvalidRequestError, match="collides"):
        build_feature_plan_from_canonical_spec(_with_predicate(predicate))
    same = {**P_ADX, "left": _feature("ema", 200, source="close")}
    build_feature_plan_from_canonical_spec(_with_predicate(same))


def test_feature_shared_with_existing_blocker_is_planned_and_computed_once() -> None:
    spec = _with_predicate(P_RANGE)
    spec["components"]["blockers"] = [copy.deepcopy(_RSI_BLOCKER)]
    labels = [
        f.output_id for f in build_feature_plan_from_canonical_spec(spec).indicator_plan.features
    ]
    assert labels.count("rsi_close_base_14") == 1
    _, context = _run([_variant("shared", spec)])
    assert _calls(context, "indicator.rsi") == 1


# -- semantics on real fixture data (tasks 4.5, 4.8) -----------------------------

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def _naive_value(operand: dict[str, Any], frame: Any, bar: int, plan_label: dict[str, str]) -> Any:
    if "const" in operand:
        return float(operand["const"])
    if "price" in operand:
        return float(getattr(frame.market_bars[bar], operand["price"]))
    value = frame.series[plan_label[repr(operand)]][bar]
    return None if value is None else float(value)


def _naive(predicate: dict[str, Any], side: str, frame: Any, labels: dict[str, str]) -> list[bool]:
    effective = dict(predicate)
    if side == "short" and "short" in predicate:
        effective.update(predicate["short"])
    out: list[bool] = []
    for bar in range(len(frame.time_ms)):
        if effective["kind"] == "compare":
            left = _naive_value(effective["left"], frame, bar, labels)
            right = _naive_value(effective["right"], frame, bar, labels)
            ok = (
                left is not None
                and right is not None
                and math.isfinite(left)
                and math.isfinite(right)
                and _OPS[effective["op"]](left, right)
            )
        else:
            value = _naive_value(effective["operand"], frame, bar, labels)
            ok = (
                value is not None
                and math.isfinite(value)
                and effective["min"] <= value <= effective["max"]
            )
        out.append(bool(ok))
    return out


_LABELS = {
    repr(ADX_1H): "adx_close_1h_14",
    repr(RSI): "rsi_close_base_14",
    repr(EMA_1H_100): "ema_close_1h_100",
    repr(EMA_1H_500): "ema_close_1h_500",
}


def test_predicates_match_a_naive_per_bar_reference() -> None:
    recorder, _ = _run([_variant("combo", _spec(_composite()))])
    capture = recorder.captures[0]
    frame = capture.frame
    for side in ("long", "short"):
        mask = _mask(capture, "combo", side)
        for child_id, predicate in PREDICATES.items():
            expected = _naive(predicate, side, frame, _LABELS)
            assert list(mask.trace[f"child:{child_id}"]) == expected, (side, child_id)
            assert any(expected), (side, child_id)  # the fixture exercises both values
            assert not all(expected), (side, child_id)
    long_rsi = _mask(capture, "combo", "long").trace["child:rsi"]
    short_rsi = _mask(capture, "combo", "short").trace["child:rsi"]
    assert long_rsi != short_rsi  # explicit short override


def test_htf_operand_is_the_aligned_plan_column() -> None:
    recorder, _ = _run([_variant("adx", _with_predicate(P_ADX))])
    capture = recorder.captures[0]
    column = capture.frame.series["adx_close_1h_14"]
    mask = _mask(capture, "combo", "long").trace["child:p"]
    assert list(mask) == [value is not None and float(value) >= 25 for value in column]
    # Completed-bar alignment: the value only changes on 1h boundaries.
    first = next(index for index, value in enumerate(column) if value is not None)
    for index in range(first + 1, len(column)):
        if (capture.frame.time_ms[index] // 60_000) % 60:
            assert column[index] == column[index - 1]


# -- sharing, sides and memo (tasks 4.4, 4.6, 4.8) --------------------------------


def test_three_predicates_on_one_column_convert_it_once() -> None:
    three = {
        "a": {"kind": "compare", "left": RSI, "op": "<", "right": {"const": 70}},
        "b": {"kind": "compare", "left": RSI, "op": ">", "right": {"const": 30}},
        "c": P_RANGE,
    }
    _, context = _run([_variant("three", _spec(_composite(predicates=three)))])
    assert _calls(context, "predicate.column") == 1
    assert context.stats.unforeseen_consumptions == 0


def test_side_free_predicate_is_computed_once_for_both_sides() -> None:
    _, context = _run([_variant("adx", _with_predicate(P_ADX))])
    assert _calls(context, "predicate.compare") == 1
    _, context = _run([_variant("rsi", _with_predicate(P_RSI))])
    assert _calls(context, "predicate.compare") == 2  # explicit short override


def test_threshold_sweep_shares_columns_and_children() -> None:
    variants = [
        _variant(
            f"adx-{threshold}",
            _spec(_composite(predicates={**PREDICATES, "adx": {**P_ADX, "right": {"const": t}}})),
        )
        for threshold, t in (("20", 20), ("25", 25), ("30", 30))
    ]
    _, context = _run(variants)
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.column") == 4
    assert _calls(context, "indicator.adx") == 1
    # Unchanged children once per batch; the swept one once per value.
    assert _calls(context, "predicate.range") == 1
    compare_calls = _calls(context, "predicate.compare")
    assert compare_calls == 3 + 2 + 2 + 1  # adx x3, rsi and ema per side, price once


def test_memo_on_and_off_are_identical() -> None:
    variants = [
        _variant("a", _spec(_composite("a"))),
        _variant("b", _spec(_composite("b"), _untouched("x"))),
        _variant("c", _with_predicate(P_RSI)),
    ]
    on, context = _run(variants, memo_enabled=True)
    off, _ = _run(variants, memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    for left, right in zip(on.captures, off.captures, strict=True):
        for left_side, right_side in zip(
            left.evaluation.setups, right.evaluation.setups, strict=True
        ):
            assert left_side.setups_ok == right_side.setups_ok
            for left_mask, right_mask in zip(left_side.setups, right_side.setups, strict=True):
                assert left_mask.final_setup_allowed == right_mask.final_setup_allowed
                if left_mask.component_id == "composite_setup":
                    assert left_mask.trace == right_mask.trace
        assert left.evaluation.entries == right.evaluation.entries


# -- live history (task 4.7) -----------------------------------------------------


def test_live_history_of_non_temporal_predicate_is_zero_additional() -> None:
    requirements = EmaPullbackLiveCalculationRequirements().execute(_with_predicate(P_ADX))
    predicate_entries = [item for item in requirements if "predicate" in item.reason]
    assert [item.bars for item in predicate_entries] == [0]


# -- hand-built frame: non-finite values (design D5, task 4.8) -------------------


def _hand_frame(values: list[float | None], closes: list[float]) -> Any:
    bars = tuple(
        SimpleNamespace(open=c, high=c, low=c, close=c, volume=1.0, open_time_ms=i)
        for i, c in enumerate(closes)
    )
    return SimpleNamespace(
        series={"f": tuple(values)},
        time_ms=tuple(range(len(values))),
        market_bars=bars,
        market_arrays=None,
    )


def test_non_finite_operands_are_false_on_a_hand_built_frame() -> None:
    feature = Operand(feature=PlannedFeature("f", "x", "base"))
    frame = _hand_frame(
        [None, math.inf, -math.inf, math.nan, 10.0, 30.0], [1.0, 1.0, 1.0, 1.0, 50.0, 5.0]
    )

    def run(condition: Any) -> list[bool]:
        return evaluate_predicate(Predicate(condition, None), frame, "long").tolist()

    assert run(Compare(feature, ">", Operand(const=20.0))) == [False] * 5 + [True]
    assert run(Compare(feature, "<", Operand(const=20.0))) == [False] * 4 + [True, False]
    assert run(Compare(Operand(price="close"), ">", feature)) == [False] * 4 + [True, False]
    assert run(Range(feature, 10.0, 30.0)) == [False] * 4 + [True, True]
    assert run(Range(feature, 10.5, 29.5)) == [False] * 6
