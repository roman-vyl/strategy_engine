"""weighted_vote_setup (OpenSpec `weighted-vote-setup-v1`): validation (group 1), evaluation
against a brute-force per-bar reference in exact decimals (group 2), evidence (group 3), identity,
sharing and cost (group 4), feature and history plans (group 5) and parity across `/range`,
`/range-batch` and `/live-entry` (group 5a). The vote tables here are arbitrary test numbers."""

from __future__ import annotations

import copy
import itertools
import json
import math
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from parity.corpus import _untouched, _variant, base_spec
from parity.harness import Recorder, batch_payload, market_fixture_meta, recording_services
from parity.managed_invariants import _bar, _slice_services
from test_ema_pullback_band_filter_e2e import WINDOW, _a1
from test_ema_pullback_predicates_band import _market_frame
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.adapters.http import strategy_routes
from strategy_engine.adapters.http.app import create_app
from strategy_engine.adapters.http.models import StrategyRangeRequestModel
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate
from strategy_engine.strategies.ema_pullback.setups import _weighted_vote_compute
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)
from strategy_engine.strategies.ema_pullback.weighted_vote_spec import (
    parse_weighted_vote_setup,
)

Spec = dict[str, Any]

RSI = {"feature": {"kind": "rsi", "params": {"period": 14}}}
CLOSE = {"price": "close"}
A1 = _a1(None, None)["operand"]
ALWAYS = {"kind": "compare", "left": CLOSE, "op": ">", "right": {"const": 0}}
UP_BAR = {"kind": "compare", "left": CLOSE, "op": ">", "right": {"price": "open"}}


def _operand_input(input_id: str, operand: Spec, direction: str, steps: list[Spec]) -> Spec:
    return {"input_id": input_id, "operand": operand, "direction": direction, "steps": steps}


def _count_input(input_id: str, of: list[Spec], steps: list[Spec]) -> Spec:
    return {"input_id": input_id, "count": {"of": of}, "steps": steps}


def _voter(voter_id: str, *inputs: Spec, role: str = "vote") -> Spec:
    return {"voter_id": voter_id, "role": role, "inputs": list(inputs)}


def _vote(threshold: float, *voters: Spec, instance_id: str = "vote") -> Spec:
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": instance_id,
        "params": {"threshold": threshold, "voters": list(voters)},
    }


def _ladder(*levels: tuple[float, float | None]) -> list[Spec]:
    return [
        {"level": level, "veto": True} if weight is None else {"level": level, "weight": weight}
        for level, weight in levels
    ]


def _table_vote(
    threshold: float = 0.5,
    a1_steps: list[Spec] | None = None,
    voter_id: str = "pullback",
    instance_id: str = "vote",
) -> Spec:
    """A vote over an episode ratio operand and a count of two predicates."""

    return _vote(
        threshold,
        _voter(
            voter_id,
            _operand_input(
                "a1",
                A1,
                "at_most",
                a1_steps or _ladder((0.8, 0.3), (0.3, 0.5), (0.05, None)),
            ),
        ),
        _voter(
            "chorus",
            _count_input(
                "bars",
                [UP_BAR, {"kind": "range", "operand": RSI, "min": 60, "max": None}],
                _ladder((1, 0.3), (2, 0.4)),
            ),
        ),
        instance_id=instance_id,
    )


def _spec(*setups: Spec) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    spec["setups"] = list(setups)
    return spec


def _mask(capture: Any, side: str, instance_id: str = "vote") -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    return next(item for item in side_eval.setups if item.instance_id == instance_id)


# -- group 1: parse and validate ------------------------------------------------------------


def test_valid_vote_passes_static_validation() -> None:
    check_ema_pullback_static_semantics(_spec(_table_vote()))


def _invalid(mutate: Any) -> Spec:
    vote = _table_vote()
    mutate(vote["params"])
    return _spec(vote)


def _first_input(params: Spec) -> Spec:
    return params["voters"][0]["inputs"][0]


def _count(params: Spec) -> Spec:
    return params["voters"][1]["inputs"][0]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.pop("threshold"), id="no-threshold"),
        pytest.param(lambda p: p.update(threshold=0), id="zero-threshold"),
        pytest.param(lambda p: p.update(threshold=-1), id="negative-threshold"),
        pytest.param(lambda p: p.update(threshold=math.inf), id="infinite-threshold"),
        pytest.param(lambda p: p.update(threshold=True), id="bool-threshold"),
        pytest.param(lambda p: p.update(threshold=0.1234567891), id="ten-digit-threshold"),
        pytest.param(lambda p: p.update(voters=[]), id="no-voters"),
        pytest.param(lambda p: p.update(extra=1), id="unknown-param"),
        pytest.param(
            lambda p: p["voters"].append(copy.deepcopy(p["voters"][0])), id="duplicate-voter-id"
        ),
        pytest.param(lambda p: p["voters"][0].update(voter_id="a/b"), id="slash-voter-id"),
        pytest.param(lambda p: p["voters"][0].update(role="gate"), id="unknown-role"),
        pytest.param(lambda p: p["voters"][0].update(inputs=[]), id="no-inputs"),
        pytest.param(lambda p: p["voters"][0].update(extra=1), id="unknown-voter-key"),
        pytest.param(lambda p: _count(p).update(input_id="a1"), id="duplicate-input-id"),
        pytest.param(lambda p: _first_input(p).update(input_id="a/b"), id="slash-input-id"),
        pytest.param(lambda p: _first_input(p).pop("direction"), id="operand-no-direction"),
        pytest.param(lambda p: _first_input(p).update(direction="above"), id="bad-direction"),
        pytest.param(lambda p: _count(p).update(direction="at_most"), id="count-with-direction"),
        pytest.param(
            lambda p: _first_input(p).update(count={"of": [ALWAYS]}), id="operand-and-count"
        ),
        pytest.param(lambda p: _first_input(p).pop("operand"), id="neither-operand-nor-count"),
        pytest.param(lambda p: _count(p).update(count={"of": []}), id="empty-count"),
        pytest.param(lambda p: _count(p)["count"].update(k=2), id="unknown-count-key"),
        pytest.param(lambda p: _first_input(p).update(steps=[]), id="no-steps"),
        pytest.param(lambda p: _first_input(p).update(extra=1), id="unknown-input-key"),
        pytest.param(
            lambda p: _first_input(p)["steps"].append({"level": 0.8, "weight": 0.1}),
            id="duplicate-level",
        ),
        pytest.param(lambda p: _first_input(p)["steps"][0].update(level=math.nan), id="nan-level"),
        pytest.param(lambda p: _first_input(p)["steps"][0].update(level=True), id="bool-level"),
        pytest.param(lambda p: _first_input(p)["steps"][0].pop("level"), id="no-level"),
        pytest.param(lambda p: _first_input(p)["steps"][0].update(veto=True), id="weight-and-veto"),
        pytest.param(lambda p: _first_input(p)["steps"][0].pop("weight"), id="no-weight-no-veto"),
        pytest.param(
            lambda p: _first_input(p)["steps"][2].update(veto=1), id="veto-not-literal-true"
        ),
        pytest.param(lambda p: _first_input(p)["steps"][0].update(weight=-0.1), id="neg-weight"),
        pytest.param(lambda p: _first_input(p)["steps"][0].update(weight=True), id="bool-weight"),
        pytest.param(
            lambda p: _first_input(p)["steps"][0].update(weight=0.1234567891), id="ten-digits"
        ),
        pytest.param(lambda p: _first_input(p)["steps"][0].update(extra=1), id="unknown-step"),
        pytest.param(lambda p: _count(p)["steps"][1].update(level=3), id="count-level-above"),
        pytest.param(lambda p: _count(p)["steps"][0].update(level=0), id="count-level-zero"),
        pytest.param(lambda p: _count(p)["steps"][0].update(level=1.5), id="count-level-float"),
        pytest.param(lambda p: p["voters"][0].update(role="veto"), id="veto-voter-with-weight"),
        pytest.param(lambda p: _first_input(p).update(operand={"const": 1}), id="const-operand"),
        pytest.param(lambda p: _first_input(p).update(operand=UP_BAR), id="predicate-as-operand"),
        pytest.param(
            lambda p: _first_input(p).update(
                operand={
                    "kind": "change",
                    "operand": RSI,
                    "lookback": 1,
                    "op": ">",
                    "value": 0,
                }
            ),
            id="change-predicate-as-operand",
        ),
        pytest.param(
            lambda p: _count(p)["count"]["of"].append({"kind": "compare"}),
            id="invalid-count-predicate",
        ),
    ],
)
def test_invalid_vote_is_rejected(mutate: Any) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_invalid(mutate))


def test_undeclared_episode_is_rejected_by_the_predicate_layer() -> None:
    spec = _spec(_table_vote())
    spec["ema_stack_episode"] = {}
    with pytest.raises(InvalidRequestError, match="not declared"):
        check_ema_pullback_static_semantics(spec)


def test_veto_voter_with_only_veto_steps_is_valid() -> None:
    vote = _vote(
        1, _voter("v", _operand_input("x", RSI, "at_least", _ladder((80, None))), role="veto")
    )
    check_ema_pullback_static_semantics(_spec(vote))


def test_vote_inside_a_composite_is_rejected() -> None:
    composite = {
        "component_id": "composite_setup",
        "instance_id": "combo",
        "params": {
            "children": [
                {
                    "child_id": "v",
                    "setup": {
                        "component_id": "weighted_vote_setup",
                        "params": _table_vote()["params"],
                    },
                }
            ],
            "paths": [{"path_id": "p", "require": ["v"]}],
        },
    }
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec(composite))


def test_weights_and_threshold_are_exact_decimals() -> None:
    vote = parse_weighted_vote_setup(
        _vote(0.75, _voter("a", _count_input("x", [ALWAYS], _ladder((1, 0.1))))), "s"
    )
    assert vote.threshold == 750_000_000
    assert vote.voters[0].inputs[0].steps[0].weight == 100_000_000
    integer = _vote(2, _voter("a", _count_input("x", [ALWAYS], _ladder((1, 1)))))
    assert parse_weighted_vote_setup(integer).threshold == 2_000_000_000
    assert (
        parse_weighted_vote_setup(
            _vote(0.123456789, _voter("a", _count_input("x", [ALWAYS], _ladder((1, 0.1)))))
        ).threshold
        == 123_456_789
    )


# -- group 2: evaluation on a synthetic market ----------------------------------------------


def _frame(market: MarketFrame, *items: Spec) -> Any:
    features: list[Any] = []
    for item in items:
        for vote_input in parse_weighted_vote_setup(item, "s").inputs():
            for raw in vote_input.predicates():
                for feature in parse_predicate(raw, "p").features():
                    if feature not in features:
                        features.append(feature)
    return RangeIndicatorEvaluator().evaluate_native(market, IndicatorPlan("1", tuple(features)))


def _compute(item: Spec, frame: Any, side: str = "long") -> tuple[tuple[bool, ...], Spec]:
    return _weighted_vote_compute(
        parse_weighted_vote_setup(item, "s"), frame, side, context=None, inputs=None
    )


def _decimal(value: float) -> Decimal:
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def _reference(item: Spec, trace: Spec) -> tuple[list[bool], list[Decimal], list[object]]:
    """A naive per-bar loop over the input values of the trace, in Decimal."""

    params = item["params"]
    length = len(trace["score"])
    allowed: list[bool] = []
    scores: list[Decimal] = []
    reasons: list[object] = []
    for t in range(length):
        total = Decimal(0)
        vetoes: list[str] = []
        for voter in params["voters"]:
            voter_weight, voter_veto = Decimal(0), False
            for vote_input in voter["inputs"]:
                value = trace[f"input:{vote_input['input_id']}:value"][t]
                weight, veto = Decimal(0), False
                for step in vote_input["steps"]:
                    if value is None:
                        continue
                    if "count" in vote_input or vote_input["direction"] == "at_least":
                        crossed = value >= step["level"]
                    else:
                        crossed = value <= step["level"]
                    if not crossed:
                        continue
                    if step.get("veto"):
                        veto = True
                    else:
                        weight = max(weight, _decimal(step["weight"]))
                assert trace[f"input:{vote_input['input_id']}:weight"][t] == float(weight)
                assert trace[f"input:{vote_input['input_id']}:veto"][t] == veto
                voter_weight, voter_veto = max(voter_weight, weight), voter_veto or veto
            assert trace[f"voter:{voter['voter_id']}:weight"][t] == float(voter_weight)
            assert trace[f"voter:{voter['voter_id']}:veto"][t] == voter_veto
            total += voter_weight
            if voter_veto:
                vetoes.append(voter["voter_id"])
        by_score = total >= _decimal(params["threshold"])
        allowed.append(not (vetoes or by_score))
        scores.append(total)
        reasons.append(f"veto:{vetoes[0]}" if vetoes else ("score" if by_score else None))
    return allowed, scores, reasons


SYNTHETIC = _vote(
    0.7,
    _voter(
        "level",
        _operand_input("rsi_low", RSI, "at_most", _ladder((45, 0.2), (35, 0.35), (25, None))),
        _operand_input("rsi_high", RSI, "at_least", _ladder((55, 0.1), (65, 0.3))),
    ),
    _voter("price", _operand_input("close", CLOSE, "at_least", _ladder((80, 0.25), (90, 0.4)))),
    _voter(
        "chorus",
        _count_input(
            "bars",
            [UP_BAR, {"kind": "range", "operand": RSI, "min": 50, "max": None}],
            _ladder((1, 0.1), (2, 0.3)),
        ),
    ),
    _voter("hard", _operand_input("rsi_veto", RSI, "at_least", _ladder((75, None))), role="veto"),
)


@pytest.mark.parametrize("side", ["long", "short"])
def test_evaluation_matches_a_brute_force_reference(side: str) -> None:
    market = _market_frame(600)
    frame = _frame(market, SYNTHETIC)
    local, trace = _compute(SYNTHETIC, frame, side)
    allowed, scores, reasons = _reference(SYNTHETIC, trace)
    assert list(local) == allowed
    assert list(trace["score"]) == [float(score) for score in scores]
    assert list(trace["blocked_by"]) == reasons
    assert {None, "score"} <= set(reasons) and any(str(r).startswith("veto:") for r in reasons)
    assert any(value is None for value in trace["input:rsi_low:value"])  # RSI warm-up
    rsi = next(iter(frame.series.values()))
    assert [None if v is None or not math.isfinite(v) else v for v in rsi] == list(
        trace["input:rsi_low:value"]
    )
    closes = [float(bar.close) for bar in market.bars]
    assert list(trace["input:close:value"]) == closes


def test_value_exactly_on_a_level_crosses_it() -> None:
    market = _market_frame(50)
    close = float(market.bars[10].close)
    vote = _vote(1, _voter("c", _operand_input("c", CLOSE, "at_most", _ladder((close, 0.5)))))
    _, trace = _compute(vote, _frame(market, vote))
    assert trace["input:c:weight"][10] == 0.5
    at_least = _vote(1, _voter("c", _operand_input("c", CLOSE, "at_least", _ladder((close, 0.5)))))
    _, trace = _compute(at_least, _frame(market, at_least))
    assert trace["input:c:weight"][10] == 0.5


def test_permuting_steps_and_inputs_changes_nothing() -> None:
    market = _market_frame(400)
    frame = _frame(market, SYNTHETIC)
    base_local, base_trace = _compute(SYNTHETIC, frame)
    permuted = copy.deepcopy(SYNTHETIC)
    for voter in permuted["params"]["voters"]:
        voter["inputs"].reverse()
        for vote_input in voter["inputs"]:
            vote_input["steps"].reverse()
    local, trace = _compute(permuted, frame)
    assert local == base_local
    assert trace == base_trace


def test_permuting_voters_changes_only_blocked_by() -> None:
    market = _market_frame(400)
    frame = _frame(market, SYNTHETIC)
    double_veto = copy.deepcopy(SYNTHETIC)
    double_veto["params"]["voters"].append(
        _voter(
            "hard2", _operand_input("rsi_veto2", RSI, "at_least", _ladder((70, None))), role="veto"
        )
    )
    base_local, base_trace = _compute(double_veto, frame)
    reversed_vote = copy.deepcopy(double_veto)
    reversed_vote["params"]["voters"].reverse()
    local, trace = _compute(reversed_vote, frame)
    assert local == base_local
    changed = {key for key in base_trace if trace[key] != base_trace[key]}
    assert changed == {"blocked_by"}
    both = [
        t
        for t in range(len(local))
        if base_trace["voter:hard:veto"][t] and base_trace["voter:hard2:veto"][t]
    ]
    assert both
    assert all(base_trace["blocked_by"][t] == "veto:hard" for t in both)
    assert all(trace["blocked_by"][t] == "veto:hard2" for t in both)


def _always_vote(threshold: float, *weights: float) -> Spec:
    return _vote(
        threshold,
        *(
            _voter(f"v{index}", _count_input(f"i{index}", [ALWAYS], _ladder((1, weight))))
            for index, weight in enumerate(weights)
        ),
    )


@pytest.mark.parametrize("order", list(itertools.permutations([0.3, 0.25, 0.2])))
def test_exact_sum_on_the_threshold_in_every_order(order: tuple[float, ...]) -> None:
    market = _market_frame(30)
    vote = _always_vote(0.75, *order)
    local, trace = _compute(vote, _frame(market, vote))
    assert not any(local)
    assert set(trace["blocked_by"]) == {"score"}
    assert set(trace["score"]) == {0.75}


def test_classic_binary_case_is_blocked() -> None:
    assert 0.1 + 0.7 < 0.8  # binary floating point would miss the threshold
    market = _market_frame(30)
    vote = _always_vote(0.8, 0.1, 0.7)
    local, _ = _compute(vote, _frame(market, vote))
    assert not any(local)


def test_just_below_the_threshold_is_not_blocked() -> None:
    market = _market_frame(30)
    vote = _always_vote(0.75, 0.5, 0.249999999)
    local, trace = _compute(vote, _frame(market, vote))
    assert all(local)
    assert set(trace["blocked_by"]) == {None}


def test_veto_alone_blocks_with_zero_weights() -> None:
    market = _market_frame(30)
    vote = _vote(
        1,
        _voter("w", _count_input("w", [ALWAYS], _ladder((1, 0)))),
        _voter("v", _count_input("v", [ALWAYS], _ladder((1, None))), role="veto"),
    )
    local, trace = _compute(vote, _frame(market, vote))
    assert not any(local)
    assert set(trace["score"]) == {0.0}
    assert set(trace["blocked_by"]) == {"veto:v"}


@pytest.mark.parametrize(("empty", "expected"), [("block", 2), ("pass", 3)])
def test_count_with_a_missing_operand(empty: str, expected: int) -> None:
    market = _market_frame(60)
    missing = {"kind": "range", "operand": RSI, "min": 0, "max": None, "empty": empty}
    vote = _vote(1, _voter("c", _count_input("c", [ALWAYS, missing, ALWAYS], _ladder((2, 0.5)))))
    _, trace = _compute(vote, _frame(market, vote))
    # bar 0: RSI(14) is missing, so B is False (block) or True (pass)
    assert trace["input:c:value"][0] == expected
    assert trace["input:c:weight"][0] == 0.5


def test_no_lookahead_on_a_truncated_market() -> None:
    market = _market_frame(500)
    full_local, full_trace = _compute(SYNTHETIC, _frame(market, SYNTHETIC))
    cut = 320
    truncated = MarketFrame(
        market.market,
        TimeRange(market.bars[0].open_time_ms, market.bars[cut].open_time_ms),
        market.bars[:cut],
        "truncated-hash",
    )
    local, trace = _compute(SYNTHETIC, _frame(truncated, SYNTHETIC))
    assert local == full_local[:cut]
    for key, values in trace.items():
        assert values == full_trace[key][:cut], key


# -- groups 2-4 on the real fixture through the pipeline ---------------------------------------


def test_vote_is_and_composed_and_reads_the_same_values_as_a_composite_child() -> None:
    child = {
        "component_id": "composite_setup",
        "instance_id": "a1_child",
        "params": {
            "children": [{"child_id": "a1", "predicate": _a1(None, None)}],
            "paths": [{"path_id": "p", "require": ["a1"]}],
        },
    }
    recorder, context = _run([_variant("v", _spec(_table_vote(), child, _untouched("u")))])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.ratio") == 2  # shared by the vote and the child
    for side in ("long", "short"):
        vote = _mask(capture, side)
        assert (
            vote.trace["input:a1:value"] == _mask(capture, side, "a1_child").trace["child:a1:value"]
        )
        allowed, _, reasons = _reference(_table_vote(), vote.trace)
        assert list(vote.local_setup_allowed) == allowed
        assert list(vote.trace["blocked_by"]) == reasons
        assert {None, "score"} <= set(reasons)
        assert any(str(reason).startswith("veto:") for reason in reasons)
        side_eval = next(item for item in capture.evaluation.setups if item.side == side)
        finals = [item.final_setup_allowed for item in side_eval.setups]
        assert side_eval.setups_ok == tuple(all(bars) for bars in zip(*finals, strict=True))
    long_values = _mask(capture, "long").trace["input:a1:value"]
    short_values = _mask(capture, "short").trace["input:a1:value"]
    assert long_values != short_values  # each side reads its own operand with one table


def test_vote_can_be_context_gated_like_any_setup() -> None:
    spec = _spec(_table_vote())
    spec["contexts"] = {
        "htf": {
            "component_id": "htf_context",
            "timeframe": "1h",
            "source": "close",
            "fast_period": 20,
            "anchor_period": 50,
            "slow_period": 200,
        }
    }
    spec["setups"][0]["context_consumption"] = {
        "context_ref": "htf",
        "policy": {"policy_id": "htf_regime_gate", "params": {"allowed_regimes": ["aligned"]}},
    }
    recorder, context = _run([_variant("gated", spec)])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        mask = _mask(capture, side)
        assert mask.context_gate_allowed is not None
        assert mask.final_setup_allowed == tuple(
            a and b
            for a, b in zip(mask.local_setup_allowed, mask.context_gate_allowed, strict=True)
        )


def test_candidates_differing_only_in_the_table_compute_each_operand_once() -> None:
    variants = [
        _variant("a", _spec(_table_vote(0.5))),
        _variant("b", _spec(_table_vote(0.6))),
        _variant("c", _spec(_table_vote(0.5, _ladder((0.7, 0.2), (0.2, 0.6))))),
        _variant("d", _spec(_table_vote(0.5, _ladder((0.8, 0.3), (0.3, 0.5), (0.1, None))))),
    ]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.segment") == 4  # two legs per side
    assert _calls(context, "predicate.ratio") == 2
    assert _calls(context, "predicate.compare") == 1  # side-free
    assert _calls(context, "predicate.range") == 1
    assert _calls(context, "setup.weighted_vote") == 4 * 2
    assert all(count == 1 for count in context.stats.compute_calls.values())


def test_a_changed_voter_id_changes_only_the_vote_node() -> None:
    recorder, context = _run(
        [
            _variant("a", _spec(_table_vote())),
            _variant("b", _spec(_table_vote(voter_id="renamed"))),
            _variant("c", _spec(_table_vote(instance_id="other"))),
        ]
    )
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.ratio") == 2
    # the instance_id is a label outside the node; the voter_id names the evidence
    assert _calls(context, "setup.weighted_vote") == 2 * 2
    a, b, c = recorder.captures
    for side in ("long", "short"):
        assert _mask(a, side).local_setup_allowed == _mask(b, side).local_setup_allowed
        assert "voter:renamed:weight" in _mask(b, side).trace
        assert "voter:pullback:weight" not in _mask(b, side).trace
        assert _mask(c, side, "other").trace == _mask(a, side).trace


def test_a_spec_without_a_vote_has_no_vote_node() -> None:
    _, context = _run([_variant("plain", base_spec())])
    assert _calls(context, "setup.weighted_vote") == 0
    assert context.stats.unforeseen_consumptions == 0


# -- group 5: plans ---------------------------------------------------------------------------


def _as_composite_child(predicate: Spec) -> Spec:
    return {
        "component_id": "composite_setup",
        "instance_id": "c",
        "params": {
            "children": [{"child_id": "x", "predicate": predicate}],
            "paths": [{"path_id": "p", "require": ["x"]}],
        },
    }


def _labels(spec: Spec) -> list[str]:
    plan = build_feature_plan_from_canonical_spec(spec)
    return [feature.output_id for feature in plan.indicator_plan.features]


def test_feature_plan_of_vote_inputs_equals_composite_children() -> None:
    rsi_range = {"kind": "range", "operand": RSI, "min": 60, "max": None}
    vote = _vote(1, _voter("r", _operand_input("r", RSI, "at_least", _ladder((60, 0.5)))))
    assert _labels(_spec(vote)) == _labels(_spec(_as_composite_child(rsi_range)))
    counted = _vote(1, _voter("r", _count_input("r", [rsi_range], _ladder((1, 0.5)))))
    assert _labels(_spec(counted)) == _labels(_spec(_as_composite_child(rsi_range)))
    both = _vote(
        1,
        _voter("a", _operand_input("a", RSI, "at_least", _ladder((60, 0.5)))),
        _voter("b", _count_input("b", [rsi_range], _ladder((1, 0.5)))),
    )
    labels = _labels(_spec(both))
    assert len(labels) == len(set(labels))  # one feature, planned once


def test_live_history_of_a_vote_equals_its_inputs_as_composite_children() -> None:
    resolver = EmaPullbackLiveCalculationRequirements()
    vote = resolver.execute(_spec(_table_vote()))
    children = resolver.execute(
        _spec(
            _as_composite_child(_a1(None, None)),
            _as_composite_child(UP_BAR),
            _as_composite_child({"kind": "range", "operand": RSI, "min": 60, "max": None}),
        )
    )
    assert max(item.bars for item in vote) == max(item.bars for item in children)
    assert sorted(item.bars for item in vote) == sorted(item.bars for item in children)


# -- group 5a: /range, /range-batch and /live-entry ---------------------------------------------


def test_range_equals_range_batch_byte_for_byte() -> None:
    variant = _variant("vote", _spec(_table_vote()))
    payload = batch_payload([variant])
    with recording_services(Recorder()) as services:
        from parity.harness import _drain_route

        ndjson = _drain_route(services, payload)
        assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
        model = StrategyRangeRequestModel.model_validate(
            json.loads(
                json.dumps(
                    {
                        "market": payload["market"],
                        "strategy": variant["strategy"],
                        "expected_market_data_hash": payload["expected_market_data_hash"],
                    }
                )
            )
        )
        result = strategy_routes.evaluate_strategy_range(model, services)
    line = json.dumps({"variant_id": "vote", "result": result, "error": None}) + "\n"
    assert line == ndjson["lines"][0]


def _live_side(client: TestClient, spec: Spec, index: int) -> str | None:
    meta = market_fixture_meta()
    response = client.post(
        "/v1/strategy-evaluations/live-entry",
        json={
            "strategy_id": "ema_pullback",
            "raw_spec": spec,
            "ticker": meta["ticker"],
            "base_timeframe": meta["timeframe"],
            "target_bar_open_time_ms": _bar(index).open_time_ms,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    entry = body.get("desired_entry")
    return None if entry is None else str(entry["side"])


def test_live_entry_equals_the_historical_decision_on_the_same_bar() -> None:
    voted = _spec(_table_vote())
    plain = _spec()
    recorder, _ = _run([_variant("voted", voted), _variant("plain", plain)])
    voted_capture, plain_capture = recorder.captures
    voted_entries = {
        item.bar_index: item.side for item in voted_capture.projection.entry_opportunities
    }
    plain_entries = {
        item.bar_index: item.side for item in plain_capture.projection.entry_opportunities
    }
    blocked = sorted(set(plain_entries) - set(voted_entries))
    kept = sorted(voted_entries)
    assert blocked and kept
    # late bars: the live window must rebuild the episode from bounded history
    targets = [*kept[-3:], *blocked[-3:], max(set(range(4000, 4100)) - set(plain_entries))]
    with _slice_services() as services, TestClient(create_app(services=services)) as client:
        for index in targets:
            assert _live_side(client, voted, index) == voted_entries.get(index), index
