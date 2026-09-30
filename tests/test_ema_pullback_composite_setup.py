"""composite_setup (OpenSpec `composite-setup-pre-entry-predicates-v1`,
groups 1-2): structural validation, path semantics against a naive per-bar
reference, reuse of semantic setups unchanged, memo parity and live
history."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import pytest
from parity.corpus import _untouched, _variant, _width, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]


def _child(child_id: str, setup: dict[str, Any]) -> dict[str, Any]:
    return {
        "child_id": child_id,
        "setup": {"component_id": setup["component_id"], "params": setup["params"]},
    }


def _composite(
    instance_id: str, children: list[dict[str, Any]], paths: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "component_id": "composite_setup",
        "instance_id": instance_id,
        "params": {"children": children, "paths": paths},
    }


def _spec_with_setups(*setups: dict[str, Any]) -> Spec:
    spec = base_spec()
    spec["setups"] = list(setups)
    return spec


W_LO = _width("w_lo", min_current_width_atr=1)
W_HI = _width("w_hi", min_current_width_atr=3)
U = _untouched("u")


def _owner_like_composite(instance_id: str = "combo") -> dict[str, Any]:
    return _composite(
        instance_id,
        [_child("w_hi", W_HI), _child("w_lo", W_LO), _child("u", U)],
        [
            {"path_id": "developed", "require": ["w_hi"]},
            {"path_id": "alternate", "at_least": {"k": 2, "of": ["w_lo", "u"]}},
        ],
    )


def _run(
    variants: list[dict[str, Any]], *, memo_enabled: bool = True
) -> tuple[list[Any], Any]:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(
        recorder, memo_enabled=memo_enabled
    ) as services:
        ndjson = _drain_route(services, batch_payload(variants))
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    for capture in recorder.captures:
        assert capture.exception is None, capture.exception
    return [capture.evaluation for capture in recorder.captures], contexts[0]


def _setup_masks(evaluation: Any, instance_id: str) -> dict[str, Any]:
    return {
        side.side: next(item for item in side.setups if item.instance_id == instance_id)
        for side in evaluation.setups
    }


# -- static validation (tasks 1.2, 1.3) ----------------------------------------------


def test_owner_like_composite_is_valid() -> None:
    check_ema_pullback_static_semantics(_spec_with_setups(_owner_like_composite()))


def _invalid(mutate: Any) -> Spec:
    composite = _owner_like_composite()
    mutate(composite)
    return _spec_with_setups(composite)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: c["params"].update(children=[]), id="no-children"),
        pytest.param(lambda c: c["params"].update(paths=[]), id="no-paths"),
        pytest.param(
            lambda c: c["params"]["children"].append(copy.deepcopy(c["params"]["children"][0])),
            id="duplicate-child-id",
        ),
        pytest.param(
            lambda c: c["params"]["paths"].append({"path_id": "developed", "require": ["u"]}),
            id="duplicate-path-id",
        ),
        pytest.param(
            lambda c: c["params"]["paths"][0].update(require=["missing"]), id="unknown-ref"
        ),
        pytest.param(
            lambda c: c["params"]["children"].append(_child("unused", U)), id="unreferenced"
        ),
        pytest.param(lambda c: c["params"]["paths"][0].pop("require"), id="empty-path"),
        pytest.param(
            lambda c: c["params"]["paths"][1]["at_least"].update(k=3), id="k-above-of"
        ),
        pytest.param(lambda c: c["params"]["paths"][1]["at_least"].update(k=0), id="k-zero"),
        pytest.param(
            lambda c: c["params"]["paths"][0].update(require=["w_hi", "w_hi"]),
            id="repeated-ref",
        ),
        pytest.param(
            lambda c: c["params"]["children"][0]["setup"].update(instance_id="x"),
            id="nested-instance-id",
        ),
        pytest.param(
            lambda c: c["params"]["children"][0]["setup"].update(
                context_consumption={"context_ref": "htf"}
            ),
            id="nested-gate",
        ),
        pytest.param(
            lambda c: c["params"]["children"][0]["setup"].update(component_id="composite_setup"),
            id="nested-composite",
        ),
        pytest.param(
            lambda c: c["params"]["children"][0]["setup"].update(
                component_id="counter_candle_blocker"
            ),
            id="non-setup-child",
        ),
        pytest.param(
            lambda c: c["params"]["children"][0].update(predicate={"kind": "compare"}),
            id="both-setup-and-predicate",
        ),
        pytest.param(lambda c: c["params"]["children"][0].update(child_id="a/b"), id="slash"),
        pytest.param(lambda c: c.update(instance_id="a/b"), id="slash-instance"),
    ],
)
def test_invalid_composite_is_rejected(mutate: Any) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_invalid(mutate))


def test_top_level_instance_colliding_with_child_key_is_rejected() -> None:
    spec = _spec_with_setups(_owner_like_composite("combo"), _width("combo/w_hi"))
    with pytest.raises(InvalidRequestError, match="collides"):
        check_ema_pullback_static_semantics(spec)


# -- evaluation (tasks 2.2, 2.5) -----------------------------------------------------


def test_single_child_composite_equals_the_plain_setup() -> None:
    composite = _composite("combo", [_child("w", W_LO)], [{"path_id": "p", "require": ["w"]}])
    evaluations, _ = _run(
        [
            _variant("plain", _spec_with_setups(W_LO)),
            _variant("composite", _spec_with_setups(composite)),
        ]
    )
    plain = _setup_masks(evaluations[0], "w_lo")
    wrapped = _setup_masks(evaluations[1], "combo")
    for side in plain:
        assert wrapped[side].local_setup_allowed == plain[side].local_setup_allowed
        assert wrapped[side].final_setup_allowed == plain[side].final_setup_allowed
        assert any(plain[side].local_setup_allowed)


def test_single_child_composite_adds_no_feature_computation() -> None:
    composite = _composite("combo", [_child("w", W_LO)], [{"path_id": "p", "require": ["w"]}])
    counts = []
    for spec in (_spec_with_setups(W_LO), _spec_with_setups(composite)):
        _, context = _run([_variant("only", spec)])
        indicator_calls: Counter[str] = Counter()
        for identity, count in context.stats.compute_calls.items():
            if identity.kind.startswith("indicator."):
                indicator_calls[identity.kind] += count
        counts.append(indicator_calls)
    assert counts[0] == counts[1]


def test_paths_match_a_naive_per_bar_reference() -> None:
    evaluations, _ = _run(
        [
            _variant("plain", _spec_with_setups(W_HI, W_LO, U)),
            _variant("composite", _spec_with_setups(_owner_like_composite())),
        ]
    )
    plain, composite = evaluations
    for side in ("long", "short"):
        hi = _setup_masks(plain, "w_hi")[side].local_setup_allowed
        lo = _setup_masks(plain, "w_lo")[side].local_setup_allowed
        u = _setup_masks(plain, "u")[side].local_setup_allowed
        mask = _setup_masks(composite, "combo")[side]
        expected_developed = hi
        expected_alternate = tuple((int(a) + int(b)) >= 2 for a, b in zip(lo, u, strict=True))
        expected = tuple(
            a or b for a, b in zip(expected_developed, expected_alternate, strict=True)
        )
        assert mask.local_setup_allowed == expected
        assert mask.trace["child:w_hi"] == hi
        assert mask.trace["child:u"] == u
        assert mask.trace["path:developed"] == expected_developed
        assert mask.trace["path:alternate"] == expected_alternate
        assert mask.trace["path:alternate:at_least_count"] == tuple(
            int(a) + int(b) for a, b in zip(lo, u, strict=True)
        )
        expected_winner = tuple(
            "developed" if d else ("alternate" if a else None)
            for d, a in zip(expected_developed, expected_alternate, strict=True)
        )
        assert mask.trace["winning_path"] == expected_winner
        # both paths occur, and some bar has both true (first declared wins)
        assert any(d and a for d, a in zip(expected_developed, expected_alternate, strict=True))
        assert any(a and not d for d, a in zip(expected_developed, expected_alternate, strict=True))


def test_composite_is_and_composed_with_other_setups() -> None:
    evaluations, _ = _run(
        [_variant("both", _spec_with_setups(_owner_like_composite(), _untouched("other")))]
    )
    for side in evaluations[0].setups:
        masks = {item.instance_id: item.final_setup_allowed for item in side.setups}
        assert side.setups_ok == tuple(
            a and b for a, b in zip(masks["combo"], masks["other"], strict=True)
        )


def test_memo_on_and_off_are_identical_with_no_unforeseen_consumptions() -> None:
    variants = [
        _variant("a", _spec_with_setups(_owner_like_composite("a"))),
        _variant("b", _spec_with_setups(_owner_like_composite("b"), W_LO)),
        _variant("c", _spec_with_setups(_owner_like_composite("c"))),
    ]
    on, context = _run(variants, memo_enabled=True)
    off, _ = _run(variants, memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    for left, right in zip(on, off, strict=True):
        for left_side, right_side in zip(left.setups, right.setups, strict=True):
            assert left_side.setups_ok == right_side.setups_ok
            assert left_side.pre_trigger_allowed == right_side.pre_trigger_allowed
            for left_mask, right_mask in zip(left_side.setups, right_side.setups, strict=True):
                assert left_mask.local_setup_allowed == right_mask.local_setup_allowed
                assert left_mask.final_setup_allowed == right_mask.final_setup_allowed
                if left_mask.component_id == "composite_setup":
                    assert left_mask.trace == right_mask.trace
        assert left.entries == right.entries


def test_same_structure_different_ids_shares_compute_but_keeps_labels() -> None:
    renamed = _composite(
        "other",
        [_child("x", W_HI), _child("y", W_LO), _child("z", U)],
        [
            {"path_id": "first", "require": ["x"]},
            {"path_id": "second", "at_least": {"k": 2, "of": ["y", "z"]}},
        ],
    )
    evaluations, context = _run(
        [
            _variant("a", _spec_with_setups(_owner_like_composite())),
            _variant("b", _spec_with_setups(renamed)),
        ]
    )
    composite_calls = sum(
        count
        for identity, count in context.stats.compute_calls.items()
        if identity.kind == "setup.composite_setup"
    )
    assert composite_calls == 2  # one per side, shared by both variants
    left = _setup_masks(evaluations[0], "combo")["long"]
    right = _setup_masks(evaluations[1], "other")["long"]
    assert left.local_setup_allowed == right.local_setup_allowed
    assert "path:first" in right.trace and "path:developed" not in right.trace
    assert set(right.trace["winning_path"]) <= {"first", "second", None}


def test_composite_can_be_context_gated_like_any_setup() -> None:
    spec = _spec_with_setups(_owner_like_composite())
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
    evaluations, _ = _run([_variant("gated", spec)])
    for side, mask in _setup_masks(evaluations[0], "combo").items():
        assert mask.context_gate_allowed is not None, side
        assert mask.final_setup_allowed == tuple(
            a and b
            for a, b in zip(mask.local_setup_allowed, mask.context_gate_allowed, strict=True)
        )


# -- live history (task 2.4) ---------------------------------------------------------


def test_live_history_of_composite_equals_its_children() -> None:
    resolver = EmaPullbackLiveCalculationRequirements()
    plain = resolver.execute(_spec_with_setups(W_HI, W_LO, U))
    composite = resolver.execute(_spec_with_setups(_owner_like_composite()))
    assert sorted(item.bars for item in plain) == sorted(item.bars for item in composite)
