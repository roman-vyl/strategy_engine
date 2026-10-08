"""EMA stack episode through the strategy pipeline (OpenSpec
`ema-stack-episode-v1`, tasks 2.1-2.2, 3.1-3.3, 4.1-4.3): the episode
operand inside `composite_setup` on real BTCUSDT.P 5m fixture data against
a naive per-bar labeller, memo reuse, static validation, live history and
the diagnostic payload."""

from __future__ import annotations

import copy
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient
from parity.corpus import _variant, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts
from test_ema_pullback_feature_range_api import payload as diagnostics_payload
from test_ema_pullback_feature_range_api import services as diagnostics_services

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)
from strategy_engine.strategies.live_calculation.indicator_requirements import ema_warmup_bars

Spec = dict[str, Any]

WINDOW = 12


def _episode(field: str, entity: str | None = None, index: Any = None) -> Spec:
    ref: Spec = {"ref": "trend", "field": field}
    if entity is not None:
        ref.update(entity=entity, index=index)
    return {"episode": ref}


PREDICATES: dict[str, Spec] = {
    "early": {"kind": "compare", "left": _episode("touch_number"), "op": "<",
              "right": {"const": 3}},
    "first_two": {"kind": "range", "operand": _episode("touch_number"), "min": 1, "max": 2},
    "leg_grows": {
        "kind": "compare",
        "left": _episode("range", "up_leg", -1),
        "op": ">",
        "right": _episode("range", "up_leg", -3),
    },
    "recent_zone": {
        "kind": "temporal",
        "mode": "within",
        "bars": 12,
        "of": {"kind": "compare", "left": _episode("in_zone"), "op": ">=",
               "right": {"const": 1}},
    },
}


def _composite(predicates: dict[str, Spec], instance_id: str = "episode") -> Spec:
    ids = list(predicates)
    return {
        "component_id": "composite_setup",
        "instance_id": instance_id,
        "params": {
            "children": [
                {"child_id": child_id, "predicate": copy.deepcopy(predicate)}
                for child_id, predicate in predicates.items()
            ],
            "paths": [{"path_id": child_id, "require": [child_id]} for child_id in ids],
        },
    }


def _spec(predicates: dict[str, Spec] | None = None, **episode: Any) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW, **episode}}
    spec["setups"] = [_composite(PREDICATES if predicates is None else predicates)]
    return spec


def _run(variants: list[Spec], *, memo_enabled: bool = True) -> tuple[Recorder, Any]:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(
        recorder, memo_enabled=memo_enabled
    ) as services:
        ndjson = _drain_route(services, batch_payload(variants))
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    for capture in recorder.captures:
        assert capture.exception is None, capture.exception
    return recorder, contexts[0]


def _calls(context: Any, kind: str) -> int:
    return sum(
        count for identity, count in context.stats.compute_calls.items() if identity.kind == kind
    )


def _child(capture: Any, side: str, child_id: str) -> list[bool]:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return list(mask.trace[f"child:{child_id}"])


def _naive_touch_numbers(capture: Any, side: str) -> list[float]:
    """An independent per-bar v6 labeller (touch number only)."""

    frame = capture.frame
    columns = capture.plan.episode_columns_by_ref["trend"]
    sign = 1.0 if side == "long" else -1.0

    def series(label: str) -> list[float]:
        return [math.nan if v is None else sign * float(v) for v in frame.series[label]]

    fast, anchor, slow = (series(columns[role]) for role in ("fast", "anchor", "slow"))
    bars = frame.market_bars
    high = [sign * float(b.high if side == "long" else b.low) for b in bars]
    low = [sign * float(b.low if side == "long" else b.high) for b in bars]
    close = [sign * float(b.close) for b in bars]
    warm_up = ema_warmup_bars(500)
    out: list[float] = []
    phase = "off"
    count = violation = run = last = 0
    censored = False
    for i in range(len(bars)):
        a = anchor[i]
        held = fast[i] > a > slow[i]
        if phase == "off":
            if held:
                phase, count, violation, censored = "away", 0, 0, i < warm_up
                out.append(math.nan if censored else 0.0)
            else:
                out.append(math.nan)
            continue
        violation = 0 if held else violation + 1
        if violation > WINDOW:
            out.append(math.nan if censored else float(count))
            phase = "off"
            continue
        if phase == "away":
            if low[i - 1] > anchor[i - 1] and low[i] <= a:
                count += 1
                phase, last, run = "zone", i, 1 if high[i] < a else 0
        elif phase == "zone":
            if low[i] > a:
                run = 0
                if i - last > WINDOW:
                    phase = "away"
            elif high[i] < a:
                run += 1
                if run > WINDOW:
                    phase = "fb"
            else:
                last, run = i, 0
        elif close[i] > a:
            phase = "away"
        out.append(math.nan if censored else float(count))
    return out


def test_episode_operands_end_to_end() -> None:
    recorder, context = _run([_variant("episode", _spec())])
    (capture,) = recorder.captures
    assert context.stats.unforeseen_consumptions == 0
    episodes = capture.evaluation.contexts.episodes
    assert episodes is not None
    assert capture.evaluation.contexts.to_wire()["items"] == {}  # not a context
    coverage = {child_id: 0 for child_id in PREDICATES}
    for side in ("long", "short"):
        naive = _naive_touch_numbers(capture, side)
        projection = episodes.side("trend", side)
        assert [
            math.isnan(a) and math.isnan(b) or a == b
            for a, b in zip(projection.state["touch_number"].tolist(), naive, strict=True)
        ] == [True] * len(naive)
        early = [math.isfinite(n) and n < 3 for n in naive]
        first_two = [math.isfinite(n) and 1 <= n <= 2 for n in naive]
        assert _child(capture, side, "early") == early
        assert _child(capture, side, "first_two") == first_two
        zone = projection.state["in_zone"].tolist()
        recent = [
            any(zone[j] == 1.0 for j in range(max(0, i - 11), i + 1)) for i in range(len(zone))
        ]
        assert _child(capture, side, "recent_zone") == recent
        # up_leg[-1].range > up_leg[-3].range, from the entity table by hand.
        touches = projection.touches
        rows = {
            (int(e), int(k)): r
            for r, (e, k) in enumerate(
                zip(touches["episode_id"].tolist(), touches["number"].tolist(), strict=True)
            )
        }
        expected = []
        for i, number in enumerate(projection.state["touch_number"].tolist()):
            if not math.isfinite(number) or number < 4:
                expected.append(False)
                continue
            episode_id = int(projection.state["episode_id"][i])
            older = rows[(episode_id, int(number) - 3)]
            newer = rows[(episode_id, int(number) - 1)]
            legs = touches["up_high"] - touches["up_low"]
            expected.append(bool(legs[newer] > legs[older]))
        assert _child(capture, side, "leg_grows") == expected
        for child_id in PREDICATES:
            coverage[child_id] += sum(_child(capture, side, child_id))
    assert all(count > 0 for count in coverage.values()), coverage


def test_memo_on_and_off_are_identical_and_the_episode_is_shared() -> None:
    variants = [
        _variant("a", _spec()),
        _variant("b", _spec({"early": PREDICATES["early"]})),
        _variant("c", _spec(PREDICATES, history_bars=15000)),
    ]
    on, context = _run(variants, memo_enabled=True)
    off, _ = _run(variants, memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "episode.ema_stack") == 2  # once per side for the whole batch
    assert _calls(context, "predicate.episode_operand") > 0
    for left, right in zip(on.captures, off.captures, strict=True):
        for left_side, right_side in zip(
            left.evaluation.setups, right.evaluation.setups, strict=True
        ):
            for left_mask, right_mask in zip(left_side.setups, right_side.setups, strict=True):
                assert left_mask.trace == right_mask.trace
                assert left_mask.final_setup_allowed == right_mask.final_setup_allowed
        assert left.evaluation.entries == right.evaluation.entries


def test_other_parameters_are_another_episode() -> None:
    _, context = _run([_variant("a", _spec()), _variant("b", _spec(window_bars=6))])
    assert _calls(context, "episode.ema_stack") == 4
    assert context.stats.unforeseen_consumptions == 0


def test_spec_without_episode_plans_and_computes_nothing_new() -> None:
    spec = base_spec()
    plan = build_feature_plan_from_canonical_spec(spec)
    assert plan.episode_columns_by_ref == {}
    assert "episode_columns_by_ref" not in plan.to_wire()
    _, context = _run([_variant("plain", spec)])
    assert not any(
        identity.kind.startswith(("episode.", "predicate.episode"))
        for identity in context.stats.compute_calls
    )


def test_episode_emas_reuse_the_stack_columns() -> None:
    spec = _spec()
    plan = build_feature_plan_from_canonical_spec(spec)
    assert plan.episode_columns_by_ref["trend"] == plan.anchor_columns
    plain = build_feature_plan_from_canonical_spec(base_spec())
    assert plan.indicator_plan.features == plain.indicator_plan.features


# -- static validation (task 3.1, 2.1) ---------------------------------------------


def _with_gate(spec: Spec, context_ref: str) -> Spec:
    spec["setups"][0]["context_consumption"] = {
        "context_ref": context_ref,
        "policy": {"policy_id": "htf_regime_gate", "params": {"allowed_regimes": ["aligned"]}},
    }
    return spec


def test_valid_spec_passes() -> None:
    check_ema_pullback_static_semantics(_spec())


@pytest.mark.parametrize(
    "spec",
    [
        _with_gate(_spec(), "trend"),
        _spec({"bad": {"kind": "compare", "left": _episode("touch_number", None),
                       "op": "<", "right": {"const": 3}}}) | {"ema_stack_episode": {}},
        _spec({"bad": {"kind": "change", "operand": _episode("touch_number"), "lookback": 2,
                       "op": ">", "value": 0}}),
        _spec({"bad": {"kind": "compare", "left": {"price": "close"}, "op": ">",
                       "right": {"const": 1}, "short": {"left": _episode("touch_number")}}}),
        _spec({"bad": {"kind": "compare", "left": _episode("touch_number"), "op": "<",
                       "right": {"const": 3}, "short": {"right": {"price": "close"}}}}),
        _spec({"bad": {"kind": "compare", "left": _episode("range", "zone", "forming"),
                       "op": ">", "right": {"const": 1}}}),
        _spec(fast_period=2000),
    ],
)
def test_invalid_episode_use_is_rejected(spec: Spec) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(spec)


def test_episode_ref_must_not_be_a_context_ref() -> None:
    spec = _spec()
    spec["contexts"] = {
        "trend": {"component_id": "htf_context", "timeframe": "1h", "source": "close",
                  "fast_period": 20, "anchor_period": 50, "slow_period": 100}
    }
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(spec)


def test_short_override_of_an_episode_predicate_may_change_op_and_constants() -> None:
    check_ema_pullback_static_semantics(
        _spec({"ok": {"kind": "compare", "left": _episode("touch_number"), "op": "<",
                      "right": {"const": 3}, "short": {"op": "<=", "right": {"const": 2}}}})
    )


# -- live history (task 4.2) -------------------------------------------------------------


def test_live_history_entry_per_episode() -> None:
    requirements = EmaPullbackLiveCalculationRequirements().execute(_spec())
    episode = [item for item in requirements if item.reason.startswith("ema_stack_episode.")]
    assert [(item.timeframe, item.bars) for item in episode] == [("base", 15000)]
    plain = EmaPullbackLiveCalculationRequirements().execute(base_spec())
    assert not any(item.reason.startswith("ema_stack_episode.") for item in plain)


# -- result payload (task 2.2) ------------------------------------------------------------


def test_diagnostics_carry_the_episode_and_unchanged_contexts() -> None:
    body_payload = diagnostics_payload()
    raw_spec = body_payload["strategy"]["raw_spec"]  # type: ignore[index]
    raw_spec["ema_stack_episode"] = {"stack": {"window_bars": 2}}
    app_services, _ = diagnostics_services()
    with TestClient(create_app(services=app_services)) as client:
        with_episode = client.post(
            "/v1/strategy-evaluations/range/diagnostics", json=body_payload
        ).json()
        without = client.post(
            "/v1/strategy-evaluations/range/diagnostics", json=diagnostics_payload()
        ).json()
    assert "ema_stack_episode" not in without
    assert with_episode["contexts"] == without["contexts"]
    item = with_episode["ema_stack_episode"]["items"]["stack"]
    assert item["params"]["window_bars"] == 2
    assert set(item["sides"]) == {"long", "short"}
    long = item["sides"]["long"]
    assert set(long) == {"state", "episodes", "zones", "false_breaks", "waves"}
    assert len(long["state"]["touch_number"]) == with_episode["market"]["bar_count"]


# -- managed phase condition --------------------------------------------------------


def _managed_spec() -> Spec:
    from parity.composite_phase_corpus import MFE_PCT, _composite, _cond, _pred
    from parity.composite_phase_corpus import _spec as managed_spec

    spec = managed_spec(
        _composite(
            [
                _pred("early", PREDICATES["early"]),
                _pred("deep", {"kind": "compare",
                               "left": _episode("depth", "false_break", 0),
                               "op": ">", "right": {"const": 0}}),
                _cond("pct", MFE_PCT),
            ],
            [{"path_id": "p", "require": ["pct"], "at_least": {"k": 1, "of": ["early", "deep"]}}],
        )
    )
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    return spec


def test_episode_operand_in_a_managed_phase_condition() -> None:
    from strategy_engine.strategies.ema_pullback.managed_composite import (
        composites_need_context_bundle,
    )

    spec = _managed_spec()
    check_ema_pullback_static_semantics(spec)
    assert composites_need_context_bundle(spec)
    on, context = _run([_variant("managed", spec)], memo_enabled=True)
    off, _ = _run([_variant("managed", spec)], memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.episode_operand") > 0
    assert on.captures[0].projection is not None
    assert on.captures[0].projection == off.captures[0].projection
