"""W8p end to end (OpenSpec `w8p-at-point-v1`): the at_point operand, parsing and placement,
the inner ratio read on the peak or the origin of the current touch through the strategy
pipeline on the BTCUSDT.P 5m fixture, a veto step, shared nodes and a spec without the operand.
The fixture has no open interest, so the field is `close`; open interest is the same column
path (`test_rolling_extreme.py`)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_predicates_a2 import _legs, _parse
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

Spec = dict[str, Any]

WINDOW = 12
PERIOD = 96
INNER = {
    "ratio": {
        "left": {"price": "close"},
        "right": {
            "feature": {"kind": "rolling_max", "source": "close", "params": {"period": PERIOD}}
        },
    }
}


def _at(point: str = "peak", inner: Spec = INNER) -> Spec:
    return {"at_point": {"episode": "trend", "point": point, "operand": inner}}


def test_at_point_parses_and_nests_in_ratio_difference_and_abs() -> None:
    operand = _parse(_at()).long.operand
    assert operand.at_point.point == "peak" and operand.at_point.operand.ratio is not None
    assert _parse(_at("origin")).long.operand.at_point.point == "origin"
    assert _parse({"abs": _at()}).long.operand.absolute.at_point is not None
    ratio = {"ratio": {"left": _at(), "right": {"price": "close"}}}
    assert _parse(ratio).long.operand.ratio.left.at_point is not None
    difference = {"difference": {"left": _at(), "right": _at("origin")}}
    assert _parse(difference).long.operand.difference.right.at_point is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"point": "peak", "operand": INNER},
        {"episode": "trend", "operand": INNER},
        {"episode": "trend", "point": "peak"},
        {"episode": "trend", "point": "entry", "operand": INNER},
        {"episode": "other", "point": "peak", "operand": INNER},
        {"episode": "trend", "point": "peak", "operand": {"const": 1.0}},
        {"episode": "trend", "point": "peak", "operand": _at()},
        {"episode": "trend", "point": "peak", "operand": INNER, "extra": 1},
    ],
)
def test_malformed_at_point_is_rejected(payload: Spec) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"at_point": payload})


def test_at_point_is_not_a_change_operand() -> None:
    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _at(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


def _probe(point: str) -> Spec:
    branch = {
        "kind": "range",
        "operand": _at(point),
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "w8p", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["w8p"]}],
        },
    }


def _vote(level: float) -> Spec:
    vote_input = {
        "input_id": "w8p",
        "operand": _at(),
        "direction": "at_most",
        "steps": [{"level": level, "veto": True}],
    }
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "w8p", "role": "vote", "inputs": [vote_input]}],
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


def _expected(capture: Any, side: str, point: str = "peak") -> np.ndarray:
    episode = capture.evaluation.contexts.episodes.side("trend", side)
    close = np.array([float(b.close) for b in capture.frame.market_bars])
    inner = np.full(len(close), math.nan)
    for t in range(PERIOD - 1, len(close)):
        inner[t] = close[t] / close[t - PERIOD + 1 : t + 1].max()
    out = np.full(len(close), math.nan)
    for t in range(len(close)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        out[t] = inner[peak if point == "peak" else origin]
    return out


@pytest.mark.parametrize("point", ["peak", "origin"])
def test_values_match_the_loop(point: str) -> None:
    probe, _ = _run([_variant("probe", _spec(_probe(point)))])
    (capture,) = probe.captures
    for side in ("long", "short"):
        expected = _expected(capture, side, point)
        trace = _mask(capture, side).trace["child:w8p:value"]
        values = np.array([math.nan if v is None else v for v in trace], dtype=float)
        assert np.isfinite(expected).sum() > 20, "fixture must give values"
        np.testing.assert_allclose(values, expected, rtol=1e-12, equal_nan=True)


def test_veto_matches_the_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe("peak")))])
    expected = {side: _expected(probe.captures[0], side) for side in ("long", "short")}
    finite = np.unique(expected["long"][np.isfinite(expected["long"])])
    level = float((finite[len(finite) // 5] + finite[len(finite) // 5 + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_vote(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        value = expected[side]
        blocked = np.isfinite(value) & (value <= level)
        assert blocked.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_nodes() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(0.95 + 0.01 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.at_point") == 2  # one per side
    assert _calls(context, "indicator.rolling_max") == 1


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.at_point") == 0
