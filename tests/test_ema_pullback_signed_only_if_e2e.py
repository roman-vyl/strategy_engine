"""Wk and D1v end to end (OpenSpec `signed-only-if-operands-v1`): the signed and only_if
operands, parsing and placement, values through the strategy pipeline on the BTCUSDT.P 5m fixture
against the raw candle features, shared nodes and a spec without the operands."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_predicates_a2 import _parse
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

Spec = dict[str, Any]

WINDOW = 12


def _feature(kind: str, timeframe: str, params: Spec) -> Spec:
    return {"feature": {"kind": kind, "timeframe": timeframe, "params": params}}


BODY = _feature("candle_body_atr", "1d", {"period": 14})
POS = _feature("candle_close_position", "1d", {})
WEEK = _feature("candle_body_atr", "1w", {"period": 14})
D1 = {
    "forming_candle": {
        "episode": "trend",
        "timeframe": "1d",
        "atr": {"kind": "atr_wilder", "timeframe": "1d", "params": {"period": 14}},
    }
}
BODY_LEVEL = 0.3  # low enough for the short fixture to open the gate on both sides
POS_LEVEL = 0.6
WK = {"signed": {"operand": WEEK, "center": 0}}
D1V = {
    "only_if": {
        "operand": D1,
        "require": [
            {"operand": {"signed": {"operand": BODY, "center": 0}}, "min": BODY_LEVEL, "max": None},
            {"operand": {"signed": {"operand": POS, "center": 0.5}}, "min": POS_LEVEL, "max": None},
        ],
    }
}


def _raw(operand: Spec) -> Spec:
    return {"ratio": {"left": operand, "right": {"const": 1.0}}}


def test_signed_and_only_if_parse_and_nest() -> None:
    assert _parse(WK).long.operand.signed.center == 0
    only_if = _parse(D1V).long.operand.only_if
    assert len(only_if.require) == 2 and only_if.require[1].min == POS_LEVEL
    assert _parse({"abs": WK}).long.operand.absolute.signed is not None
    ratio = {"ratio": {"left": D1V, "right": {"const": 2.0}}}
    assert _parse(ratio).long.operand.ratio.left.only_if is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"signed": {"operand": WEEK}},
        {"signed": {"center": 0}},
        {"signed": {"operand": {"const": 1.0}, "center": 0}},
        {"signed": {"operand": WEEK, "center": "a"}},
        {"signed": {"operand": WEEK, "center": 0, "extra": 1}},
        {"only_if": {"operand": D1}},
        {"only_if": {"operand": D1, "require": []}},
        {"only_if": {"operand": {"const": 1.0}, "require": D1V["only_if"]["require"]}},
        {
            "only_if": {
                "operand": D1,
                "require": [{"operand": BODY, "min": 1, "max": None, "empty": "pass"}],
            }
        },
        {"only_if": {"operand": D1, "require": [{"operand": {"const": 1}, "min": 1, "max": None}]}},
        {"only_if": {"operand": D1, "require": [{"operand": BODY, "min": 2, "max": 1}]}},
    ],
)
def test_malformed_operands_are_rejected(payload: Spec) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(payload)


@pytest.mark.parametrize("operand", [WK, D1V])
def test_not_a_change_operand(operand: Spec) -> None:
    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": operand, "lookback": 3, "op": ">", "value": 0},
            "p",
            episode_refs=["trend"],
        )


def _branch(operand: Spec) -> Spec:
    return {
        "kind": "range",
        "operand": operand,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }


CHILDREN = {
    "wk": WK,
    "d1v": D1V,
    "week": _raw(WEEK),
    "body": _raw(BODY),
    "pos": _raw(POS),
    "d1": _raw(D1),
}


def _probe() -> Spec:
    children = [{"child_id": key, "predicate": _branch(op)} for key, op in CHILDREN.items()]
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": children,
            "paths": [{"path_id": "pass", "require": list(CHILDREN)}],
        },
    }


def _vote(level: float) -> Spec:
    vote_input = {
        "input_id": "wk",
        "operand": WK,
        "direction": "at_least",
        "steps": [{"level": level, "veto": True}],
    }
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "wk", "role": "vote", "inputs": [vote_input]}],
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


def _trace(mask: Any, child: str) -> np.ndarray:
    return np.array([math.nan if v is None else v for v in mask.trace[f"child:{child}:value"]])


def test_values_match_the_raw_features() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    for side in ("long", "short"):
        mask = _mask(capture, side)
        g = 1.0 if side == "long" else -1.0
        week, body, pos, d1 = (_trace(mask, k) for k in ("week", "body", "pos", "d1"))
        np.testing.assert_array_equal(_trace(mask, "wk"), g * week)
        signed_pos = pos if side == "long" else 0.5 - (pos - 0.5)
        with np.errstate(invalid="ignore"):
            gate = (g * body >= BODY_LEVEL) & (signed_pos >= POS_LEVEL)
        expected = np.where(gate & np.isfinite(d1), d1, math.nan)
        assert np.isfinite(expected).sum() > 0, "fixture must open the gate"
        assert (np.isfinite(d1) & ~gate).any(), "fixture must close the gate"
        np.testing.assert_array_equal(_trace(mask, "d1v"), expected)


def test_candidates_differing_only_in_a_level_share_the_nodes() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(0.5 + 0.1 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.signed") == 2  # one per side


def test_a_spec_without_the_operands_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.signed") == 0
    assert _calls(context, "predicate.only_if") == 0
