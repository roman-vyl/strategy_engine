"""composite_phase_condition (OpenSpec `composite-managed-phase-condition-v1`,
groups 1, 2 and 4): static contract, single-trade replay (`/managed-replay`
and live open-trade) against a naive per-bar reference on the parity market
fixture, and feature/live-history planning."""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from parity.composite_phase_corpus import (
    ADX1H,
    ADX5,
    ADX_DI_1H,
    BARS,
    DI1H,
    MFE_ATR,
    MFE_PCT,
    STATE1H,
    _composite,
    _cond,
    _gt,
    _pred,
    _spec,
    mixed_at_least,
    owner_case,
    state_temporal,
    trade_only_at_least,
)
from parity.corpus import _untouched
from parity.managed_invariants import _bar, _slice_services

import strategy_engine.strategies.application.evaluate_managed_replay as replay_app
from strategy_engine.adapters.http import strategy_routes
from strategy_engine.adapters.http.models import (
    ManagedReplayRequestModel,
    OpenTradeProjectionRequestModel,
)
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.managed import (
    evaluate_start_after_entry_managed_projection,
)
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

_ENTRY_INDICES = (40, 3000, 5500, 8000)


# -- 1.3 static contract ---------------------------------------------------------


@pytest.mark.parametrize(
    "condition",
    [owner_case(), mixed_at_least(), trade_only_at_least(), state_temporal()],
    ids=["owner-case", "mixed-at-least", "trade-only-at-least", "state-temporal"],
)
def test_valid_composites_are_accepted(condition: dict[str, Any]) -> None:
    check_ema_pullback_static_semantics(_spec(condition))


def _mutate(path: str, value: Any) -> dict[str, Any]:
    condition = owner_case()
    target: Any = condition
    *keys, last = path.split(".")
    for key in keys:
        target = target[int(key)] if key.isdigit() else target[key]
    if value is _DELETE:
        del target[last]
    elif last.isdigit():
        target[int(last)] = value
    else:
        target[last] = value
    return condition


_DELETE = object()
_SETUP_CHILD = {
    "child_id": "adx5",
    "setup": {"component_id": "untouched_anchor_setup", "params": _untouched()["params"]},
}


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param(copy.deepcopy(ADX5), id="bare-predicate-as-condition"),
        pytest.param(
            _mutate("params.children.3", _cond("mfe", owner_case())), id="nested-composite"
        ),
        pytest.param(
            _mutate("params.children.3", _cond("mfe", {"component_id": "mfe_r", "params": {}})),
            id="mfe_r-child",
        ),
        pytest.param(_mutate("params.children.0", _SETUP_CHILD), id="setup-child"),
        pytest.param(
            _mutate("params.children.0", {**_pred("adx5", ADX5), **_cond("adx5", MFE_PCT)}),
            id="predicate-and-condition",
        ),
        pytest.param(
            _mutate("params.children.0", {**_pred("adx5", ADX5), "extra": 1}),
            id="unknown-child-field",
        ),
        pytest.param(
            _mutate("params.children.3", {"child_id": "mfe", "condition": {**MFE_ATR, "extra": 1}}),
            id="unknown-condition-field",
        ),
        pytest.param(_mutate("params.extra", 1), id="unknown-params-field"),
        pytest.param(_mutate("instance_id", "x"), id="unknown-condition-key"),
        pytest.param(_mutate("params.paths.0.require", ["mfe"]), id="unreferenced-child"),
        pytest.param(_mutate("params.paths.0.require", ["adx5", "nope"]), id="unknown-reference"),
        pytest.param(
            _mutate(
                "params.paths.0", {"path_id": "fast", "at_least": {"k": 0, "of": ["adx5", "mfe"]}}
            ),
            id="k-zero",
        ),
        pytest.param(
            _mutate(
                "params.paths.0", {"path_id": "fast", "at_least": {"k": 3, "of": ["adx5", "mfe"]}}
            ),
            id="k-above-len",
        ),
        pytest.param(_mutate("params.children.0.child_id", "a/b"), id="slash-in-child-id"),
        pytest.param(_mutate("params.paths.0.path_id", "a/b"), id="slash-in-path-id"),
        pytest.param(_mutate("params.paths.1.path_id", "fast"), id="duplicate-path-id"),
        pytest.param(
            _mutate("params.children.0.predicate", {**STATE1H, "context_ref": "missing"}),
            id="undeclared-context",
        ),
        pytest.param(_mutate("params.children.0.predicate.op", "!="), id="bad-predicate"),
        pytest.param(_mutate("params.paths", []), id="no-paths"),
    ],
)
def test_invalid_composites_are_rejected(condition: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec(condition))


def test_atomic_rules_are_not_newly_validated() -> None:
    # An unknown atom keeps failing where it failed before (at evaluation
    # and in live planning), not in static validation.
    check_ema_pullback_static_semantics(_spec({"component_id": "mfe_r", "params": {}}))


# -- 2.5 single-trade replay against a naive reference ---------------------------

_REGIME = {
    "long": {"up": "aligned", "down": "countertrend", "neutral": "neutral"},
    "short": {"up": "countertrend", "down": "aligned", "neutral": "neutral"},
}


class _Captured:
    frame: Any
    plan: Any
    bundle: Any


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Captured]:
    captured = _Captured()
    original = replay_app.evaluate_managed_replay

    def spy(raw_spec: Any, frame: Any, planned: Any, **kwargs: Any) -> Any:
        captured.frame, captured.plan, captured.bundle = frame, planned, kwargs.get("bundle")
        return original(raw_spec, frame, planned, **kwargs)

    monkeypatch.setattr(replay_app, "evaluate_managed_replay", spy)
    yield captured


def _replay(services: Any, spec: Spec, side: str, index: int) -> dict[str, Any]:
    from parity.harness import market_fixture_meta

    meta = market_fixture_meta()
    bar = _bar(index)
    model = ManagedReplayRequestModel.model_validate(
        {
            "market": {
                "ticker": meta["ticker"],
                "base_timeframe": meta["timeframe"],
                "from_ms": meta["from_ms"],
                "to_ms": meta["to_ms"],
            },
            "strategy": {"strategy_id": "ema_pullback", "raw_spec": spec},
            "trade_id": f"{side}-{index}",
            "side": side,
            "entry_time_ms": bar.open_time_ms,
            "entry_price": float(bar.close),
        }
    )
    return strategy_routes.evaluate_managed_replay(model, services)


def _naive_market(predicate: dict[str, Any], side: str, captured: _Captured) -> list[bool]:
    frame = captured.frame
    length = len(frame.time_ms)
    kind = predicate["kind"]
    if kind == "temporal":
        inner = _naive_market(predicate["of"], side, captured)
        bars = predicate["bars"]
        assert predicate["mode"] == "held_for"
        return [i >= bars - 1 and all(inner[i - bars + 1 : i + 1]) for i in range(length)]
    if kind == "state":
        output = next(
            o for o in captured.bundle.outputs if o.context_ref == predicate["context_ref"]
        )
        return [_REGIME[side][state] in predicate["in"] for state in output.state]
    effective = dict(predicate)
    if side == "short" and "short" in predicate:
        effective.update(predicate["short"])
    labels = {
        feature.kind: feature.output_id
        for feature in parse_predicate(predicate, "naive").features()
    }

    def value(operand: dict[str, Any], bar: int) -> float:
        if "const" in operand:
            return float(operand["const"])
        raw = frame.series[labels[operand["feature"]["kind"]]][bar]
        return math.nan if raw is None else float(raw)

    assert kind == "compare" and effective["op"] == ">"
    out = []
    for bar in range(length):
        left, right = value(effective["left"], bar), value(effective["right"], bar)
        out.append(math.isfinite(left) and math.isfinite(right) and left > right)
    return out


def _naive_adx_di(params: dict[str, Any], side: str, captured: _Captured) -> list[bool]:
    columns = captured.plan.adx_dmi_columns[(params["timeframe"], params["period"])]
    series = {name: captured.frame.series[columns[name]] for name in ("adx", "di_plus", "di_minus")}
    out = []
    for adx, plus, minus in zip(series["adx"], series["di_plus"], series["di_minus"], strict=True):
        if adx is None or plus is None or minus is None:
            out.append(False)
            continue
        aligned = float(plus) > float(minus) if side == "long" else float(minus) > float(plus)
        out.append(
            float(adx) >= params["adx_threshold"]
            and (not params["require_di_alignment"] or aligned)
        )
    return out


def _atr(captured: _Captured, period: int) -> tuple[Any, ...]:
    output_id = next(
        feature.output_id
        for feature in captured.plan.indicator_plan.features
        if feature.kind == "atr"
        and feature.timeframe == "base"
        and feature.parameters.get("period") == period
    )
    return captured.frame.series[output_id]


def _naive_trade_atom(
    atom: dict[str, Any], *, bars_in_trade: int, mfe_distance: float, entry_price: float, atr: Any
) -> bool:
    threshold = atom["params"]["threshold"]
    if atom["component_id"] == "bars_in_trade":
        return bars_in_trade >= threshold
    if atom["component_id"] == "mfe_pct":
        return mfe_distance / entry_price >= threshold
    return atr is not None and float(atr) > 0 and mfe_distance >= threshold * float(atr)


def _naive_first_transition(
    condition: dict[str, Any], side: str, entry_index: int, captured: _Captured
) -> tuple[int, str, dict[str, bool]] | None:
    """First bar from entry (offset 0) where some path is true, the first
    true path, and the values of the children that path references."""

    params = condition["params"]
    market = {}
    for child in params["children"]:
        if "predicate" in child:
            market[child["child_id"]] = _naive_market(child["predicate"], side, captured)
        elif child["condition"]["component_id"] == "adx_di_threshold":
            market[child["child_id"]] = _naive_adx_di(child["condition"]["params"], side, captured)
    trade = {
        child["child_id"]: child["condition"]
        for child in params["children"]
        if "condition" in child and child["child_id"] not in market
    }
    atr = {
        child_id: _atr(captured, atom["params"]["atr"]["period"])
        for child_id, atom in trade.items()
        if atom["component_id"] == "mfe_atr"
    }
    bars = captured.frame.market_bars
    entry_price = float(bars[entry_index].close)
    best = entry_price
    for index in range(entry_index, len(bars)):
        high, low = float(bars[index].high), float(bars[index].low)
        best = max(best, high) if side == "long" else min(best, low)
        values = {child_id: mask[index] for child_id, mask in market.items()}
        for child_id, atom in trade.items():
            values[child_id] = _naive_trade_atom(
                atom,
                bars_in_trade=index - entry_index + 1,
                mfe_distance=abs(best - entry_price),
                entry_price=entry_price,
                atr=atr[child_id][index] if child_id in atr else None,
            )
        for path in params["paths"]:
            require = path.get("require", [])
            at_least = path.get("at_least")
            if all(values[ref] for ref in require) and (
                at_least is None or sum(values[ref] for ref in at_least["of"]) >= at_least["k"]
            ):
                referenced = dict.fromkeys([*require, *(at_least["of"] if at_least else [])])
                return index, path["path_id"], {ref: values[ref] for ref in referenced}
    return None


def _phase_events(wire: dict[str, Any]) -> list[dict[str, Any]]:
    events = wire["calculation"]["events"] if "calculation" in wire else wire["events"]
    return [event for event in events if event["event_type"] == "phase_changed"]


@pytest.mark.parametrize(
    "condition",
    [owner_case(), mixed_at_least(), trade_only_at_least(), state_temporal()],
    ids=["owner-case", "mixed-at-least", "trade-only-at-least", "state-temporal"],
)
def test_replay_matches_a_naive_reference(condition: dict[str, Any], capture: _Captured) -> None:
    spec = _spec(condition)
    transitions = 0
    paths: set[str] = set()
    with _slice_services() as services:
        for side in ("long", "short"):
            for index in _ENTRY_INDICES:
                wire = _replay(services, spec, side, index)
                expected = _naive_first_transition(condition, side, index, capture)
                events = _phase_events(wire)
                if expected is None:
                    assert events == [], (side, index)
                    continue
                bar, path_id, children = expected
                assert [
                    (e["bar_index"], e["rule_id"], e["component_id"], e["to_phase"], e["metadata"])
                    for e in events
                ] == [
                    (
                        bar,
                        "rule-0",
                        "composite_phase_condition",
                        "proven",
                        {"path_id": path_id, "children": children},
                    )
                ], (side, index)
                transitions += 1
                paths.add(path_id)
    # The corpus must exercise the composite, not only its "never true" case.
    assert transitions >= 4, transitions


def test_both_owner_paths_are_attributed(capture: _Captured) -> None:
    # Find one entry per path with the naive reference, then check that the
    # replay attributes that path with the same children.
    condition = owner_case()
    spec = _spec(condition)
    with _slice_services() as services:
        _replay(services, spec, "long", 3000)
        found: dict[str, tuple[str, int, tuple[int, str, dict[str, bool]]]] = {}
        for side in ("long", "short"):
            for index in range(200, len(capture.frame.time_ms) - 1, 250):
                expected = _naive_first_transition(condition, side, index, capture)
                if expected is not None:
                    found.setdefault(expected[1], (side, index, expected))
        assert set(found) == {"fast", "htf"}
        for side, index, (bar, path_id, children) in found.values():
            (event,) = _phase_events(_replay(services, spec, side, index))
            assert (event["bar_index"], event["metadata"]) == (
                bar,
                {"path_id": path_id, "children": children},
            )


def test_di_short_override_changes_the_short_side(capture: _Captured) -> None:
    with _slice_services() as services:
        _replay(services, _spec(owner_case()), "long", 3000)
    long_di = _naive_market(DI1H, "long", capture)
    short_di = _naive_market(DI1H, "short", capture)
    side_free = {key: value for key, value in DI1H.items() if key != "short"}
    assert short_di != _naive_market(side_free, "short", capture)
    assert _naive_market(side_free, "short", capture) == long_di


def test_warm_up_bars_are_false(capture: _Captured) -> None:
    # ADX 1h > 0 is true on every ready bar: the transition lands on the
    # first bar where the 1h ADX exists, never earlier.
    condition = _composite(
        [_pred("adx1h", _gt("adx", "1h", 0))], [{"path_id": "ready", "require": ["adx1h"]}]
    )
    with _slice_services() as services:
        wire = _replay(services, _spec(condition), "long", 0)
    label = next(
        feature.output_id
        for feature in parse_predicate(
            condition["params"]["children"][0]["predicate"], "x"
        ).features()
    )
    first_ready = next(i for i, v in enumerate(capture.frame.series[label]) if v is not None)
    assert first_ready > 0
    assert [e["bar_index"] for e in _phase_events(wire)] == [first_ready]


def test_composite_of_one_atom_equals_the_atomic_rule() -> None:
    # Two single-child paths are the same OR as two atomic rules with the
    # same target; the atom formulas are the existing ones.
    composite = _composite(
        [_cond("adx_di", ADX_DI_1H), _cond("pct", MFE_PCT)],
        [{"path_id": "adx", "require": ["adx_di"]}, {"path_id": "pct", "require": ["pct"]}],
    )
    with _slice_services() as services:
        for side in ("long", "short"):
            for index in _ENTRY_INDICES:
                got = _phase_events(_replay(services, _spec(composite), side, index))
                ref = _phase_events(
                    _replay(
                        services,
                        _spec(ADX_DI_1H, MFE_PCT, to_phases=("proven", "proven")),
                        side,
                        index,
                    )
                )
                assert [e["bar_index"] for e in got] == [e["bar_index"] for e in ref]
                assert [e["metadata"]["path_id"] for e in got] == [
                    {"rule-0": "adx", "rule-1": "pct"}[e["rule_id"]] for e in ref
                ]


def test_same_bar_cascade_across_two_composite_rules() -> None:
    first = _composite(
        [_cond("bars", {"component_id": "bars_in_trade", "params": {"threshold": 3}})],
        [{"path_id": "a", "require": ["bars"]}],
    )
    second = _composite(
        [
            _cond("bars", {"component_id": "bars_in_trade", "params": {"threshold": 3}}),
            _pred("adx1h", _gt("adx", "1h", 0)),
        ],
        [{"path_id": "b", "require": ["bars", "adx1h"]}],
    )
    with _slice_services() as services:
        wire = _replay(
            services, _spec(first, second, to_phases=("proven", "protected")), "long", 3000
        )
    assert [
        (e["bar_index"], e["rule_id"], e["from_phase"], e["to_phase"], e["metadata"]["path_id"])
        for e in _phase_events(wire)
    ] == [
        (3002, "rule-0", "initial_risk", "proven", "a"),
        (3002, "rule-1", "proven", "protected", "b"),
    ]


def test_atomic_spec_builds_no_context_bundle(capture: _Captured) -> None:
    with _slice_services() as services:
        _replay(services, _spec(owner_case()), "long", 3000)
        assert capture.bundle is None
        _replay(services, _spec(state_temporal()), "long", 3000)
        assert capture.bundle is not None


# -- live open-trade -------------------------------------------------------------


@pytest.mark.parametrize(
    "condition", [owner_case(), state_temporal()], ids=["owner-case", "state-temporal"]
)
def test_live_open_trade_matches_the_start_after_entry_replay(
    condition: dict[str, Any], capture: _Captured
) -> None:
    from parity.harness import market_fixture_meta

    meta = market_fixture_meta()
    spec = _spec(condition)
    checked = 0
    with _slice_services() as services:
        _replay(services, spec, "long", 3000)  # captures the full-fixture frame
        for side in ("long", "short"):
            for index in _ENTRY_INDICES[1:]:
                plan_bar, entry_bar = _bar(index - 1), _bar(index)
                target = _bar(index + 1500)
                entry = Decimal(str(entry_bar.open))
                step = entry * Decimal("0.01")
                stop, take = (
                    (entry - step, entry + 2 * step)
                    if side == "long"
                    else (entry + step, entry - 2 * step)
                )
                model = OpenTradeProjectionRequestModel.model_validate(
                    {
                        "strategy_id": "ema_pullback",
                        "raw_spec": spec,
                        "ticker": meta["ticker"],
                        "base_timeframe": meta["timeframe"],
                        "target_bar_open_time_ms": target.open_time_ms,
                        "executed_trade_receipt": {
                            "side": side,
                            "source_plan_bar_open_time_ms": plan_bar.open_time_ms,
                            "entry_bar_open_time_ms": entry_bar.open_time_ms,
                            "planned_entry_price": str(entry),
                            "initial_stop_price": str(stop),
                            "initial_take_price": str(take),
                            "locked_exit_profile": "aligned",
                        },
                    }
                )
                live = strategy_routes.evaluate_open_trade_projection(model, services)
                reference = evaluate_start_after_entry_managed_projection(
                    spec,
                    capture.frame,
                    capture.plan,
                    side=side,  # type: ignore[arg-type]
                    entry_time_ms=entry_bar.open_time_ms,
                    planned_entry_price=entry,
                    initial_stop_price=stop,
                    initial_take_price=take,
                    target_time_ms=target.open_time_ms,
                    bundle=capture.bundle if capture.bundle is not None else _bundle(spec, capture),
                )
                got = [
                    (e["time_ms"], e["rule_id"], e["metadata"])
                    for e in live.diagnostics.managed_events
                    if e["event_type"] == "phase_changed"
                ]
                want = [
                    (e.time_ms, e.rule_id, e.metadata)
                    for e in reference.replay.events
                    if e.event_type == "phase_changed"
                ]
                assert got == want, (side, index)
                checked += len(want)
    assert checked >= 1


def _bundle(spec: Spec, captured: _Captured) -> Any:
    from strategy_engine.strategies.ema_pullback.contexts import build_context_bundle

    return build_context_bundle(spec, captured.frame, captured.plan)


# -- 4.3 planning and live history -----------------------------------------------


def _features(spec: Spec, kind: str, timeframe: str) -> list[Any]:
    plan = build_feature_plan_from_canonical_spec(spec)
    return [
        feature
        for feature in plan.indicator_plan.features
        if feature.kind == kind and feature.timeframe == timeframe
    ]


def test_predicate_children_share_the_adx_column_with_atoms_and_composite_setup() -> None:
    spec = _spec(
        _composite(
            [_pred("adx1h", ADX1H), _pred("di1h", DI1H), _cond("atom", ADX_DI_1H)],
            [{"path_id": "p", "require": ["adx1h", "di1h", "atom"]}],
        )
    )
    spec["setups"].append(
        {
            "component_id": "composite_setup",
            "instance_id": "combo",
            "params": {
                "children": [{"child_id": "adx", "predicate": copy.deepcopy(ADX1H)}],
                "paths": [{"path_id": "p", "require": ["adx"]}],
            },
        }
    )
    for kind in ("adx", "di_plus", "di_minus"):
        assert len(_features(spec, kind, "1h")) == 1, kind


def test_atom_children_are_planned_like_atomic_rules() -> None:
    composite = build_feature_plan_from_canonical_spec(
        _spec(
            _composite(
                [_cond("mfe", MFE_ATR), _cond("adx", ADX_DI_1H)],
                [{"path_id": "p", "require": ["mfe", "adx"]}],
            )
        )
    )
    atomic = build_feature_plan_from_canonical_spec(
        _spec(MFE_ATR, ADX_DI_1H, to_phases=("proven", "protected"))
    )
    assert composite.indicator_plan == atomic.indicator_plan
    assert composite.adx_dmi_columns == atomic.adx_dmi_columns


def test_predicate_label_collision_fails_closed() -> None:
    # The stack anchor already owns `ema_close_base_200` with source close.
    def child(source: str) -> dict[str, Any]:
        ema = {"feature": {"kind": "ema", "params": {"period": 200}, "source": source}}
        predicate = {"kind": "compare", "left": ema, "op": ">", "right": {"const": 0}}
        return _composite([_pred("ema", predicate)], [{"path_id": "p", "require": ["ema"]}])

    with pytest.raises(InvalidRequestError, match="collides"):
        build_feature_plan_from_canonical_spec(_spec(child("open")))
    build_feature_plan_from_canonical_spec(_spec(child("close")))


def test_live_history_of_composite_children() -> None:
    requirements = EmaPullbackLiveCalculationRequirements().execute(_spec(state_temporal()))
    by_child = {
        item.reason.split(" ")[0]: item.bars
        for item in requirements
        if item.reason.startswith("phase_rules[0].")
    }
    assert by_child == {
        "phase_rules[0].state": 0,
        "phase_rules[0].held": 5,
        "phase_rules[0].adx_di": 0,
    }


def test_unknown_child_fails_closed_in_live_history() -> None:
    from strategy_engine.strategies.ema_pullback import live_calculation_requirements as module

    requirements = module.EmaPullbackLiveCalculationRequirements()
    spec = _spec(trade_only_at_least())
    original = module._ZERO_LOOKBACK_PHASE_RULE_COMPONENTS
    try:
        module._ZERO_LOOKBACK_PHASE_RULE_COMPONENTS = original - {"mfe_pct"}
        with pytest.raises(InvalidRequestError, match="no registered live history policy"):
            requirements.execute(spec)
    finally:
        module._ZERO_LOOKBACK_PHASE_RULE_COMPONENTS = original


def test_plan_of_atomic_managed_specs_is_unchanged() -> None:
    # The group 0 gate pins plan_hash byte for byte; here: the atom planning
    # moved into a helper and plans exactly the atom columns, in rule order.
    spec = _spec(MFE_ATR, ADX_DI_1H, BARS, to_phases=("proven", "protected", "runner"))
    plan = build_feature_plan_from_canonical_spec(spec)
    no_management = copy.deepcopy(spec)
    no_management["trade_management"]["exit_management"] = {}
    base = build_feature_plan_from_canonical_spec(no_management)
    labels = [feature.output_id for feature in plan.indicator_plan.features]
    base_labels = [feature.output_id for feature in base.indicator_plan.features]
    assert labels[: len(base_labels)] == base_labels
    assert [
        (feature.kind, feature.timeframe)
        for feature in plan.indicator_plan.features[len(base_labels) :]
    ] == [("atr", "base"), ("adx", "1h"), ("di_plus", "1h"), ("di_minus", "1h")]


# -- 3.x projection `paths` ------------------------------------------------------


def _batch(variants: list[dict[str, Any]], *, memo_enabled: bool = True) -> tuple[list[Any], Any]:
    from parity.harness import Recorder, _drain_route, batch_payload, recording_services
    from parity.invariants import _capturing_contexts

    with (
        _capturing_contexts() as contexts,
        recording_services(Recorder(), memo_enabled=memo_enabled) as services,
    ):
        ndjson = _drain_route(services, batch_payload(variants))
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    return ndjson["lines"], contexts[0] if contexts else None


def _managed(line: str) -> dict[str, Any]:
    import json

    return json.loads(line)["result"]["managed"]


def _variants(*specs: Spec) -> list[dict[str, Any]]:
    from parity.corpus import _variant

    return [_variant(f"v{index}", spec) for index, spec in enumerate(specs)]


def test_projection_paths_shape() -> None:
    lines, _ = _batch(
        _variants(_spec(owner_case()), _spec(trade_only_at_least()), _spec(mixed_at_least()))
    )
    owner, trade_only, mixed = (_managed(line) for line in lines)

    (rule,) = owner["rules"]
    assert (rule["condition_id"], rule["distance_id"], rule["trade_metric"]) == (None, None, None)
    mfe = {"distance_id": "phase:rule-0:child:mfe:distance", "trade_metric": "mfe_distance"}
    assert rule["paths"] == [
        {
            "path_id": "fast",
            "condition_id": "phase:rule-0:path:fast:condition",
            "thresholds": [mfe],
            "at_least": None,
        },
        {
            "path_id": "htf",
            "condition_id": "phase:rule-0:path:htf:condition",
            "thresholds": [mfe],
            "at_least": None,
        },
    ]
    # One series per path however many market children it folds; one
    # distance per trade child however many paths use it.
    assert set(owner["conditions"]) == {
        "phase:rule-0:path:fast:condition",
        "phase:rule-0:path:htf:condition",
    }
    assert set(owner["distances"]) == {"phase:rule-0:child:mfe:distance"}

    def term(child_id: str, metric: str) -> dict[str, Any]:
        return {
            "condition_id": None,
            "distance_id": f"phase:rule-0:child:{child_id}:distance",
            "trade_metric": metric,
        }

    (rule,) = trade_only["rules"]
    assert rule["paths"] == [
        {
            "path_id": "trade",
            "condition_id": None,
            "thresholds": [],
            "at_least": {
                "k": 2,
                "terms": [
                    term("bars", "bars_since_entry"),
                    term("pct", "mfe_pct"),
                    term("mfe", "mfe_distance"),
                ],
            },
        }
    ]
    assert trade_only["conditions"] == {}

    (rule,) = mixed["rules"]
    adx5 = "phase:rule-0:child:adx5:condition"
    assert rule["paths"] == [
        {
            "path_id": "vote",
            "condition_id": "phase:rule-0:path:vote:condition",
            "thresholds": [],
            "at_least": {
                "k": 2,
                "terms": [
                    {"condition_id": adx5, "distance_id": None, "trade_metric": None},
                    term("pct", "mfe_pct"),
                    term("bars", "bars_since_entry"),
                ],
            },
        }
    ]
    assert set(mixed["conditions"]) == {"phase:rule-0:path:vote:condition", adx5}


def test_all_market_at_least_folds_into_the_path_condition() -> None:
    condition = _composite(
        [_pred("adx5", ADX5), _pred("adx1h", ADX1H), _pred("di1h", DI1H)],
        [{"path_id": "vote", "at_least": {"k": 2, "of": ["adx5", "adx1h", "di1h"]}}],
    )
    (line,), _ = _batch(_variants(_spec(condition)))
    (rule,) = _managed(line)["rules"]
    assert rule["paths"] == [
        {
            "path_id": "vote",
            "condition_id": "phase:rule-0:path:vote:condition",
            "thresholds": [],
            "at_least": None,
        }
    ]


def test_atomic_rules_serialize_without_paths() -> None:
    (line,), _ = _batch(_variants(_spec(MFE_ATR, ADX_DI_1H, to_phases=("proven", "protected"))))
    for rule in _managed(line)["rules"]:
        assert "paths" not in rule


# -- 5.3 memo --------------------------------------------------------------------


def _predicate_computes(context: Any) -> dict[Any, int]:
    return {
        identity: count
        for identity, count in context.stats.compute_calls.items()
        if identity.kind.startswith("predicate")
    }


def _with_mfe_threshold(threshold: float) -> Spec:
    condition = owner_case()
    condition["params"]["children"][3]["condition"]["params"]["threshold"] = threshold
    return _spec(condition)


def test_batch_differing_only_in_mfe_computes_each_predicate_once() -> None:
    lines, context = _batch(_variants(*(_with_mfe_threshold(t) for t in (2.0, 3.0, 4.0))))
    assert context.stats.unforeseen_consumptions == 0
    computes = _predicate_computes(context)
    # adx5, adx1h (side-free), di1h long and short, and one shared 1h column
    # node per operand feature.
    compares = [identity for identity in computes if identity.kind == "predicate.compare"]
    assert len(compares) == 4
    assert set(computes.values()) == {1}
    assert (
        len({_managed(line)["distances"]["phase:rule-0:child:mfe:distance"][-1] for line in lines})
        == 3
    )


def test_predicate_shared_with_composite_setup_is_computed_once() -> None:
    spec = _spec(owner_case())
    spec["setups"].append(
        {
            "component_id": "composite_setup",
            "instance_id": "combo",
            "params": {
                "children": [{"child_id": "adx", "predicate": copy.deepcopy(ADX1H)}],
                "paths": [{"path_id": "p", "require": ["adx"]}],
            },
        }
    )
    _, context = _batch(_variants(spec))
    assert context.stats.unforeseen_consumptions == 0
    computes = _predicate_computes(context)
    assert len([i for i in computes if i.kind == "predicate.compare"]) == 4
    assert set(computes.values()) == {1}


def test_memo_on_and_off_give_identical_projections() -> None:
    variants = _variants(
        _with_mfe_threshold(2.0),
        _with_mfe_threshold(3.0),
        _spec(state_temporal()),
        _spec(mixed_at_least()),
    )
    memo_on, context = _batch(variants, memo_enabled=True)
    memo_off, _ = _batch(variants, memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    assert memo_on == memo_off
