"""weighted_vote_setup extensions (OpenSpec `exponent-vote-weighting-v1`): `between: linear` and
`weighting.exponent`; the vote knows no trade side. Validation (group 1), evaluation against a
per-bar reference in exact rationals (group 2), evidence and identity (group 3), feature plan
(group 4). The numbers here are arbitrary test numbers."""

from __future__ import annotations

import copy
import math
from fractions import Fraction
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant
from test_ema_pullback_predicates_band import _market_frame
from test_ema_pullback_stack_episode_e2e import _calls, _run
from test_ema_pullback_weighted_vote import (
    ALWAYS,
    CLOSE,
    RSI,
    UP_BAR,
    _compute,
    _frame,
    _ladder,
    _mask,
    _operand_input,
    _spec,
    _table_vote,
    _vote,
    _voter,
)

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.setups import (
    _linear_ladder,
    _vote_input_param,
    exponent_weight,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)
from strategy_engine.strategies.ema_pullback.weighted_vote_spec import (
    Exponent,
    parse_weighted_vote_setup,
)

Spec = dict[str, Any]


def _curve_input(
    input_id: str,
    operand: Spec,
    points: list[tuple[float, float]],
    k: float | None = None,
    e_v: float | None = None,
    **extra: Any,
) -> Spec:
    item: Spec = {
        "input_id": input_id,
        "operand": operand,
        "between": "linear",
        "steps": [{"level": level, "weight": weight} for level, weight in points],
    }
    if k is not None:
        item["weighting"] = {"exponent": {"k": k, "e_v": e_v}}
    item.update(extra)
    return item


def _research_weight(e: np.ndarray, k: float, ev: float) -> np.ndarray:
    # the research lambda, copied verbatim
    return (np.exp(k * e) - 1) / (np.exp(k * ev) - 1)


# -- group 1: parse and validate ------------------------------------------------------------


MIXED = _vote(
    1.75,
    _voter("rsi", _curve_input("rsi", RSI, [(20, 26.0), (35, 10.0), (50, 0.0)], 0.15, 16)),
    _voter(
        "or",
        _curve_input("a", RSI, [(30, 20.0), (60, 0.0)], 0.3, 16),
        _curve_input("b", CLOSE, [(80, 0.0), (120, 18.0)], 0.6, 20),
    ),
    _voter("third", _curve_input("g", CLOSE, [(90, 0.0), (110, 8.0)], 0.2, 8)),
    _voter("step", _operand_input("s", RSI, "at_least", _ladder((60, 0.25), (70, 0.5)))),
    _voter("hard", _operand_input("v", RSI, "at_least", _ladder((80, None))), role="veto"),
)


def test_valid_extended_vote_passes_static_validation() -> None:
    check_ema_pullback_static_semantics(_spec(MIXED))


def _invalid(mutate: Any) -> Spec:
    vote = copy.deepcopy(MIXED)
    mutate(vote["params"])
    return _spec(vote)


def _input(params: Spec, voter: int = 0, index: int = 0) -> Spec:
    item: Spec = params["voters"][voter]["inputs"][index]
    return item


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: _input(p).update(between="cubic"), id="unknown-between"),
        pytest.param(lambda p: _input(p).update(direction="at_most"), id="linear-direction"),
        pytest.param(lambda p: _input(p)["steps"].pop() and _input(p)["steps"].pop(), id="one-pt"),
        pytest.param(lambda p: _input(p)["steps"].append({"level": 60, "veto": True}), id="veto"),
        pytest.param(lambda p: _input(p)["weighting"].update(linear=1), id="weighting-key"),
        pytest.param(lambda p: _input(p).update(weighting={}), id="empty-weighting"),
        pytest.param(lambda p: _input(p)["weighting"]["exponent"].pop("k"), id="no-k"),
        pytest.param(lambda p: _input(p)["weighting"]["exponent"].update(k=0), id="zero-k"),
        pytest.param(lambda p: _input(p)["weighting"]["exponent"].update(e_v=-1), id="neg-ev"),
        pytest.param(lambda p: _input(p)["weighting"]["exponent"].update(k=True), id="bool-k"),
        pytest.param(lambda p: _input(p)["weighting"]["exponent"].update(k=math.inf), id="inf-k"),
        pytest.param(lambda p: _input(p)["weighting"]["exponent"].update(k=50), id="overflow"),
        pytest.param(
            lambda p: _input(p)["weighting"]["exponent"].update(k=1, e_v=701), id="overflow-ev"
        ),
        pytest.param(
            lambda p: p["voters"][4]["inputs"][0].update(
                weighting={"exponent": {"k": 0.1, "e_v": 1}}
            ),
            id="exponent-on-veto",
        ),
        pytest.param(lambda p: _input(p).update(short={"operand": RSI}), id="side-in-the-vote"),
        pytest.param(lambda p: _input(p).update(when=[UP_BAR]), id="gate-in-the-vote"),
        pytest.param(
            lambda p: p["voters"].append(
                _voter(
                    "c",
                    {
                        "input_id": "c",
                        "count": {"of": [ALWAYS]},
                        "steps": _ladder((1, 0.1)),
                        "between": "linear",
                    },
                )
            ),
            id="linear-count",
        ),
    ],
)
def test_invalid_extended_vote_is_rejected(mutate: Any) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_invalid(mutate))


def test_parsed_extensions() -> None:
    spec = parse_weighted_vote_setup(MIXED)
    rsi, a, b, third, step, hard = spec.inputs()
    assert rsi.linear and rsi.direction is None and rsi.exponent == Exponent(0.15, 16.0)
    assert len(third.predicates()) == 1
    assert not step.has_extensions() and not hard.has_extensions()
    assert spec.has_exponent


# -- group 2: evaluation --------------------------------------------------------------------


def test_linear_ladder_values() -> None:
    market = _market_frame(400)
    closes = np.array([float(bar.close) for bar in market.bars])
    lo, hi = float(np.percentile(closes, 30)), float(np.percentile(closes, 70))
    vote = _vote(100, _voter("c", _curve_input("c", CLOSE, [(hi, 0.104), (lo, 16.0)])))
    _, trace = _compute(vote, _frame(market, vote))
    expected = np.interp(closes, [lo, hi], [16.0, 0.104])
    assert list(trace["input:c:weight"]) == expected.tolist()
    assert trace["input:c:weight"][int(np.argmax(closes))] == 0.104  # right of the points
    assert trace["input:c:weight"][int(np.argmin(closes))] == 16.0  # left of the points


def test_linear_ladder_scenario_and_missing_value() -> None:
    market = _market_frame(400)
    vote = _vote(100, _voter("r", _curve_input("r", RSI, [(60, 0.0), (40, 16.0)])))
    _, trace = _compute(vote, _frame(market, vote))
    values, weights = trace["input:r:value"], trace["input:r:weight"]
    assert values[0] is None and weights[0] == 0.0  # RSI warm-up
    for value, weight in zip(values, weights, strict=True):
        if value is not None:
            assert weight == float(np.interp(value, [40, 60], [16.0, 0.0]))
    vote_mid = _vote(100, _voter("r", _curve_input("r", RSI, [(0.6, 16.0), (0.7, 0.0)])))
    item = parse_weighted_vote_setup(vote_mid).inputs()[0]
    got = _linear_ladder(item, np.array([0.65, 0.5, 0.9, np.nan])).tolist()
    assert got[0] == pytest.approx(8.0) and got[1:] == [16.0, 0.0, 0.0]


def test_exponent_weight_equals_research_bit_for_bit() -> None:
    rng = np.random.default_rng(7)
    e = rng.uniform(0, 30, 10_000)
    for k, ev in ((0.15, 16.0), (0.3, 16.0), (0.6, 20.0), (0.2, 8.0), (0.01, 16.0)):
        assert np.array_equal(exponent_weight(e, Exponent(k, ev)), _research_weight(e, k, ev))
    assert exponent_weight(np.array([16.0]), Exponent(0.15, 16.0))[0] == 1.0
    assert exponent_weight(np.array([0.0]), Exponent(0.15, 16.0))[0] == 0.0
    middle = exponent_weight(np.array([8.0]), Exponent(0.15, 16.0))[0]
    assert middle == (math.exp(1.2) - 1) / (math.exp(2.4) - 1)


def _reference(item: Spec, frame: Any, trace: Spec, side: str) -> tuple[list[bool], list[str]]:
    """Per-bar loop over the traced values, weights rebuilt from the config, sum in Fraction."""

    params = item["params"]
    threshold = Fraction(repr(params["threshold"]))
    allowed: list[bool] = []
    reasons: list[str] = []
    for t in range(len(trace["score"])):
        total, vetoes = Fraction(0), []
        for voter in params["voters"]:
            voter_weight, voter_veto = Fraction(0), False
            for vote_input in voter["inputs"]:
                name = vote_input["input_id"]
                value = trace[f"input:{name}:value"][t]
                weight, veto = Fraction(0), False
                if vote_input.get("between") == "linear":
                    points = sorted((s["level"], s["weight"]) for s in vote_input["steps"])
                    x = 0.0
                    if value is not None:
                        x = float(np.interp(value, *zip(*points, strict=True)))
                    level_value: Fraction | float = x
                else:
                    level_value = Fraction(0)
                    for step in vote_input["steps"]:
                        if value is None:
                            continue
                        at_least = vote_input["direction"] == "at_least"
                        if (value >= step["level"]) if at_least else (value <= step["level"]):
                            if step.get("veto"):
                                veto = True
                            else:
                                level_value = max(level_value, Fraction(repr(step["weight"])))
                exponent = vote_input.get("weighting", {}).get("exponent")
                if exponent is not None:
                    x = float(level_value)
                    weight = Fraction(
                        float(_research_weight(np.float64(x), exponent["k"], exponent["e_v"]))
                    )
                elif isinstance(level_value, float):
                    weight = Fraction(level_value)
                else:
                    weight = level_value
                assert trace[f"input:{name}:weight"][t] == float(weight)
                voter_weight, voter_veto = max(voter_weight, weight), voter_veto or veto
            total += voter_weight
            if voter_veto:
                vetoes.append(voter["voter_id"])
        by_score = total >= threshold
        allowed.append(not (vetoes or by_score))
        reasons.append(f"veto:{vetoes[0]}" if vetoes else ("score" if by_score else None))
    return allowed, reasons


@pytest.mark.parametrize("side", ["long", "short"])
def test_evaluation_matches_an_exact_reference(side: str) -> None:
    market = _market_frame(600)
    frame = _frame(market, MIXED)
    local, trace = _compute(MIXED, frame, side)
    allowed, reasons = _reference(MIXED, frame, trace, side)
    assert list(local) == allowed
    assert list(trace["blocked_by"]) == reasons
    assert {None, "score"} <= set(reasons)
    assert any(str(reason).startswith("veto:") for reason in reasons)


def test_the_threshold_is_compared_exactly() -> None:
    market = _market_frame(50)
    flat = [(0, 0.1), (1e9, 0.1)]
    # step 0.7 (exact decimal) + linear float 0.1 (0.1000000000000000055…) > 0.8,
    # while the float64 sum 0.7 + 0.1 is 0.7999999999999999
    vote = _vote(
        0.8,
        _voter("s", _operand_input("s", CLOSE, "at_least", _ladder((0, 0.7)))),
        _voter("l", _curve_input("l", CLOSE, flat)),
    )
    local, trace = _compute(vote, _frame(market, vote))
    assert trace["score"][0] == 0.7 + 0.1 < 0.8
    assert not any(local)
    # two floats whose exact sum is below the threshold stay allowed
    below = _vote(
        0.8,
        _voter("a", _curve_input("a", CLOSE, [(0, 0.7), (1e9, 0.7)])),
        _voter("l", _curve_input("l", CLOSE, flat)),
    )
    assert Fraction(0.7) + Fraction(0.1) < Fraction("0.8")
    local, _ = _compute(below, _frame(market, below))
    assert all(local)


def test_permuting_voters_changes_no_mask() -> None:
    market = _market_frame(600)
    frame = _frame(market, MIXED)
    reordered = copy.deepcopy(MIXED)
    reordered["params"]["voters"].reverse()
    for side in ("long", "short"):
        assert _compute(MIXED, frame, side)[0] == _compute(reordered, frame, side)[0]


def test_level_value_is_traced_before_weighting() -> None:
    market = _market_frame(300)
    vote = _vote(
        100,
        _voter("x", _operand_input("x", RSI, "at_most", _ladder((50, 8.0), (30, 16.0)))),
    )
    vote["params"]["voters"][0]["inputs"][0]["weighting"] = {"exponent": {"k": 0.15, "e_v": 16}}
    _, trace = _compute(vote, _frame(market, vote))
    levels = np.array(trace["input:x:level_value"])
    assert set(levels.tolist()) <= {0.0, 8.0, 16.0}
    assert np.array_equal(np.array(trace["input:x:weight"]), _research_weight(levels, 0.15, 16))


# -- group 3: identity ----------------------------------------------------------------------


def test_plain_inputs_keep_their_identity_params() -> None:
    plain = parse_weighted_vote_setup(_table_vote()).inputs()
    assert all(len(_vote_input_param(item)) == 4 for item in plain)
    extended = parse_weighted_vote_setup(MIXED).inputs()
    assert all(len(_vote_input_param(item)) == 5 for item in extended[:4])


def test_changing_k_changes_only_the_vote_node() -> None:
    other = copy.deepcopy(MIXED)
    other["params"]["voters"][0]["inputs"][0]["weighting"]["exponent"]["k"] = 0.2
    recorder, context = _run([_variant("a", _spec(MIXED)), _variant("b", _spec(other))])
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "setup.weighted_vote") == 2 * 2
    a, b = recorder.captures
    assert _mask(a, "long").local_setup_allowed is not None
    assert _mask(b, "long").local_setup_allowed is not None
