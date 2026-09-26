"""Identity-soundness suite (OpenSpec `batch-computation-reuse`, task 3.7).

Checks the `resolve()`/`NodeSpec` identities against the contract in the
change's spec ("Semantic node identity"):

(a) semantically equivalent normalized inputs/dependencies -> same identity;
(b) semantically distinct computation -> different identity;
(c) same identity -> bit-identical computed result.

(a) and (b) are asserted on the identities themselves, i.e. on normalized
inputs and dependency structure -- never by comparing outputs. Output
bit-identity is only ever checked as the *consequence* required by (c), for
pairs whose identities are already equal, and one test pins that two
distinct computations with coincidentally equal outputs keep distinct
identities.

Inputs are the parity corpus probes/synthetic variants over the committed
MDS fixture; "bit-identical" uses the parity harness's own canonical
encoding (`snapshot.encode`: float64 raw bytes, None/NaN kept distinct).
"""

from __future__ import annotations

import functools
import itertools
import json
import math
from collections.abc import Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from parity.corpus import (
    _RSI_BLOCKER,
    _atr_exit,
    _exits,
    _width,
    _with,
    base_spec,
    probe_cases,
    synthetic_cases,
)
from parity.harness import CORPUS_DIR, _fixture_mds_client, market_fixture_meta
from parity.snapshot import ArrayStore, encode
from strategy_engine.domain.errors import StrategyEngineError
from strategy_engine.domain.market import MarketFrame, MarketStream
from strategy_engine.domain.node_identity import NodeSpec, canonical, node_spec
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import NativeFeatureFrame, PlannedFeature
from strategy_engine.indicators.implementations.range_evaluator import (
    RangeIndicatorEvaluator,
    resolve_feature,
)
from strategy_engine.indicators.market_arrays import MarketArrays
from strategy_engine.strategies.ema_pullback import exits as exits_module
from strategy_engine.strategies.ema_pullback.evaluation import (
    EmaPullbackEvaluation,
    EmaPullbackIdentity,
    evaluate_ema_pullback_frame,
    resolve_ema_pullback_frame,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
    build_feature_plan_from_canonical_spec,
    resolve_context_ema_requests,
    resolve_ema_request,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import resolve_exit_rule_groups

Spec = dict[str, Any]


# -- evaluation + resolution over the fixture market --------------------------------


@functools.lru_cache(maxsize=1)
def _market() -> tuple[MarketFrame, MarketArrays]:
    meta = market_fixture_meta()
    client = _fixture_mds_client("http://unused")
    try:
        frame = client.load_range(
            MarketStream(meta["ticker"], meta["timeframe"]),
            TimeRange(meta["from_ms"], meta["to_ms"]),
            expected_market_data_hash=meta["market_data_hash"],
        )
    finally:
        client.close()
    return frame, MarketArrays.from_market_frame(frame)


BASE_TIMEFRAME = "5m"


@dataclass(frozen=True)
class Resolved:
    raw_spec: Spec
    planned: EmaPullbackFeaturePlan
    ids: EmaPullbackIdentity


@dataclass(frozen=True)
class Evaluated(Resolved):
    frame: NativeFeatureFrame
    evaluation: EmaPullbackEvaluation


def resolve(raw_spec: Spec) -> Resolved:
    """Identity only: no market data is read."""

    planned = build_feature_plan_from_canonical_spec(raw_spec)
    return Resolved(
        raw_spec,
        planned,
        resolve_ema_pullback_frame(raw_spec, planned, base_timeframe=BASE_TIMEFRAME),
    )


def evaluate(raw_spec: Spec) -> Evaluated:
    resolved = resolve(raw_spec)
    market_frame, arrays = _market()
    assert market_frame.market.base_timeframe == BASE_TIMEFRAME
    frame = RangeIndicatorEvaluator().evaluate_native(
        market_frame, resolved.planned.indicator_plan, market_arrays=arrays
    )
    evaluation = evaluate_ema_pullback_frame(
        SimpleNamespace(raw_spec=raw_spec),  # type: ignore[arg-type]
        frame,
        resolved.planned,
    )
    return Evaluated(raw_spec, resolved.planned, resolved.ids, frame, evaluation)


def digest(value: Any) -> str:
    """Bit-exact canonical encoding (parity harness rules)."""

    if isinstance(value, pd.Series):
        value = value.to_numpy()
    return json.dumps(encode(value, ArrayStore()), sort_keys=True)


def node_outputs(item: Evaluated) -> Iterator[tuple[str, NodeSpec, str]]:
    """`(address, identity, digest of that node's full computed output)` for
    every resolved node whose output the evaluation exposes (or that the
    test recomputes through the production compute helper)."""

    ids, ev, frame = item.ids, item.evaluation, item.frame

    for output_id, node in ids.features.items():
        yield (
            f"feature:{output_id}",
            node,
            digest((frame.series[output_id], frame.validity[output_id])),
        )

    for output in ev.contexts.outputs:
        yield (
            f"context:{output.context_ref}",
            ids.contexts[output.context_ref],
            digest((output.state, output.up, output.down, output.neutral)),
        )

    gate_records = [record for record in ev.consumption if record.role != "exit_policy"]
    assert len(gate_records) == len(ids.gates)
    for record, gate in zip(gate_records, ids.gates, strict=True):
        assert (record.role, record.instance_id, record.side) == (
            gate.role,
            gate.instance_id,
            gate.side,
        )
        yield (
            f"gate:{gate.role}:{gate.instance_id}:{gate.side}",
            gate.node,
            digest((record.resolved_regime, record.allowed)),
        )

    for side_ev, side_id in zip(ev.direction_blockers, ids.direction_blockers, strict=True):
        side = side_ev.side
        assert side == side_id.side
        yield (
            f"direction:{side}",
            side_id.direction,
            digest((side_ev.direction.allowed, side_ev.direction.trace)),
        )
        for mask, (label, intrinsic), (_, allowed) in zip(
            side_ev.blockers, side_id.blocker_intrinsic, side_id.blocker_allowed, strict=True
        ):
            assert mask.instance_id == label
            yield (
                f"blocker:{label}:{side}",
                intrinsic,
                digest((mask.intrinsic_allowed, mask.trace)),
            )
            yield f"blocker-gated:{label}:{side}", allowed, digest(mask.allowed)
        yield f"blockers_ok:{side}", side_id.blockers_ok, digest(side_ev.blockers_ok)
        yield f"pre_setup:{side}", side_id.pre_setup_allowed, digest(side_ev.pre_setup_allowed)

    for side_ev, side_id in zip(ev.setups, ids.setups, strict=True):
        side = side_ev.side
        for mask, setup in zip(side_ev.setups, side_id.setups, strict=True):
            assert mask.instance_id == setup.instance_id
            yield (
                f"setup:{setup.instance_id}:{side}",
                setup.local,
                digest((mask.local_setup_allowed, mask.trace)),
            )
            yield (
                f"setup-final:{setup.instance_id}:{side}",
                setup.final,
                digest(mask.final_setup_allowed),
            )
            if setup.width_prefix is not None:
                yield (
                    f"setup-width-prefix:{setup.instance_id}",
                    setup.width_prefix,
                    digest((mask.trace["current_width_atr"], mask.trace["recent_max_width_atr"])),
                )
        yield f"setups_ok:{side}", side_id.setups_ok, digest(side_ev.setups_ok)
        yield (
            f"pre_trigger:{side}",
            side_id.pre_trigger_allowed,
            digest(side_ev.pre_trigger_allowed),
        )

    for side_ev, side_id in zip(ev.triggers, ids.triggers, strict=True):
        side = side_ev.side
        yield (
            f"trigger:{side}",
            side_id.trigger,
            digest((side_ev.trigger.allowed, side_ev.trigger.trace)),
        )
        yield (
            f"pre_risk:{side}",
            side_id.pre_risk_entry_allowed,
            digest(side_ev.pre_risk_entry_allowed),
        )

    exit_ev, exit_id = ev.exit_policy, ids.exit_policy
    yield "exit-profile:long", exit_id.profile_long, digest(exit_ev.profile_long)
    yield "exit-profile:short", exit_id.profile_short, digest(exit_ev.profile_short)
    for evidence in exit_ev.rule_evidence:
        if evidence.side is not None:
            yield (
                f"exit-signal:{evidence.instance_id}:{evidence.side}",
                exit_id.signal_rules[evidence.instance_id][evidence.side],
                digest(evidence.signal),
            )
    # Distance rules: the full (distance, ratio) output, recomputed through
    # the production helper (the evaluation exposes only the ratio).
    df = exits_module._frame_dataframe(frame)
    for rules in resolve_exit_rule_groups(item.raw_spec).values():
        for rule in rules:
            instance_id = str(rule["instance_id"])
            if instance_id in exit_id.distance_rules:
                distance, ratio = exits_module._distance(df, rule, item.planned)
                yield (
                    f"exit-distance:{instance_id}",
                    exit_id.distance_rules[instance_id],
                    digest((distance.to_numpy(), ratio.to_numpy())),
                )
    for profile, aggregate in exit_id.by_profile.items():
        yield (
            f"exit-any-signal:{profile}:long",
            aggregate.signal_long,
            digest(exit_ev.signal_by_profile_long[profile]),
        )
        yield (
            f"exit-any-signal:{profile}:short",
            aggregate.signal_short,
            digest(exit_ev.signal_by_profile_short[profile]),
        )
        yield (
            f"exit-min-sl-ratio:{profile}",
            aggregate.stop_loss_ratio,
            digest(exit_ev.stop_loss_by_profile[profile]),
        )
        yield (
            f"exit-min-tp-ratio:{profile}",
            aggregate.take_profit_ratio,
            digest(exit_ev.take_profit_by_profile[profile]),
        )
    select_fields = {
        "signal": ("signal_exit_long", "signal_exit_short"),
        "stop_loss_ratio": ("stop_loss_ratio_long", "stop_loss_ratio_short"),
        "take_profit_ratio": ("take_profit_ratio_long", "take_profit_ratio_short"),
        "stop_loss_distance": ("stop_loss_distance_long", "stop_loss_distance_short"),
        "take_profit_distance": ("take_profit_distance_long", "take_profit_distance_short"),
        "ready": ("stop_ready_long", "stop_ready_short"),
    }
    for (field, side), node in exit_id.select.items():
        attribute = select_fields[field][0 if side == "long" else 1]
        yield f"exit-select:{field}:{side}", node, digest(getattr(exit_ev, attribute))


# -- corpus -------------------------------------------------------------------------


def _corpus_specs() -> list[tuple[str, Spec]]:
    specs: list[tuple[str, Spec]] = []
    for case in synthetic_cases() + probe_cases():
        for variant in case.variants:
            specs.append((f"{case.name}/{variant['variant_id']}", variant["strategy"]["raw_spec"]))
    real_3d = json.loads((CORPUS_DIR / "real_3d_grid_subset.json").read_text())["variants"]
    for variant in real_3d[:: max(1, len(real_3d) // 12)]:
        specs.append((f"real_3d/{variant['variant_id']}", variant["strategy"]["raw_spec"]))
    return specs


@functools.lru_cache(maxsize=1)
def _evaluated_corpus() -> tuple[tuple[str, Evaluated], ...]:
    evaluated: list[tuple[str, Evaluated]] = []
    for name, raw_spec in _corpus_specs():
        try:
            evaluated.append((name, evaluate(raw_spec)))
        except StrategyEngineError:
            continue  # intended-failure probes: no node outputs to compare
    return tuple(evaluated)


# -- NodeSpec value semantics ---------------------------------------------------------


def test_canonical_parameters_are_type_tagged_and_bit_exact() -> None:
    # Python equality/hash would merge each of these pairs; the identity must not.
    assert canonical(True) != canonical(1)
    assert canonical(1) != canonical(1.0)
    assert canonical(0.0) != canonical(-0.0)
    assert canonical(float("nan")) == canonical(float("nan"))
    assert canonical("1") != canonical(1)
    assert canonical(frozenset({"a", "b"})) == canonical(frozenset({"b", "a"}))
    with pytest.raises(TypeError):
        canonical(object())


def test_node_spec_is_frozen_hashable_and_layout_canonical() -> None:
    upstream = node_spec("indicator.ema", version=1, params={"period": 5})
    left = node_spec(
        "x", version=1, params={"b": 2, "a": 1.5}, upstream={"u": upstream, "v": None}, side="long"
    )
    right = node_spec(
        "x", version=1, params={"a": 1.5, "b": 2}, upstream={"v": None, "u": upstream}, side="long"
    )
    assert left == right and hash(left) == hash(right)
    assert len({left, right}) == 1
    with pytest.raises(AttributeError):
        left.kind = "y"  # type: ignore[misc]
    assert left != node_spec(
        "x", version=2, params={"b": 2, "a": 1.5}, upstream={"u": upstream, "v": None}, side="long"
    )
    assert left != node_spec(
        "x", version=1, params={"b": 2, "a": 1.5}, upstream={"u": upstream, "v": None}
    )
    # Set-valued upstream: order- and duplicate-insensitive by construction.
    other = node_spec("indicator.ema", version=1, params={"period": 6})
    assert node_spec("m", version=1, upstream={"s": (upstream, other)}) == node_spec(
        "m", version=1, upstream={"s": (other, upstream, other)}
    )


def test_identity_never_uses_output_id() -> None:
    same_label_close = PlannedFeature("label", "ema", "base", "close", {"period": 200})
    same_label_open = PlannedFeature("label", "ema", "base", "open", {"period": 200})
    other_label_close = PlannedFeature("other", "ema", "5m", "close", {"period": 200})
    ids = [
        resolve_feature(feature, base_timeframe=BASE_TIMEFRAME, upstream={})
        for feature in (same_label_close, same_label_open, other_label_close)
    ]
    assert ids[0] != ids[1]  # same label, different computation
    assert ids[0] == ids[2]  # different label (and "base" vs "5m"), same computation
    assert all("label" not in repr(node) and "other" not in repr(node) for node in ids)


# -- (a) equivalent normalized inputs -> same identity ------------------------------------


def _setup(item: Resolved, instance_id: str, side: str) -> Any:
    side_ids = next(entry for entry in item.ids.setups if entry.side == side)
    return next(setup for setup in side_ids.setups if setup.instance_id == instance_id)


def _probe_specs(case_name: str) -> dict[str, Spec]:
    case = next(case for case in probe_cases() if case.name == case_name)
    return {variant["variant_id"]: variant["strategy"]["raw_spec"] for variant in case.variants}


def test_missing_default_equals_explicit_default() -> None:
    specs = _probe_specs("probe_default_setup_params")
    omitted = resolve(specs["untouched-lookback-omitted"])
    explicit = resolve(specs["untouched-lookback-50-explicit"])
    params_omitted = resolve(specs["untouched-params-omitted"])
    for side in ("long", "short"):
        assert (
            _setup(omitted, "untouched1", side).local == _setup(explicit, "untouched1", side).local
        )
    assert (
        resolve(specs["untouched-active-bars-omitted"]).ids.setups
        == resolve(specs["untouched-active-bars-3-explicit"]).ids.setups
    )
    # {} params: lookback=50, active_bars=3 -- same as the explicit-50 variant.
    assert (
        _setup(params_omitted, "untouched1", "long").local
        == _setup(explicit, "untouched1", "long").local
    )

    width_minimal = resolve(specs["width-minimal-params"])
    width_explicit = resolve(specs["width-explicit-defaults"])
    assert width_minimal.ids == width_explicit.ids

    components = _probe_specs("probe_default_components")
    reclaim = [
        resolve(components[name]).ids.triggers
        for name in (
            "trigger-omitted",
            "trigger-reclaim-explicit-lb1",
            "trigger-reclaim-lookback-omitted",
            "trigger-reclaim-string",
        )
    ]
    assert all(entry == reclaim[0] for entry in reclaim)
    assert resolve(components["direction-omitted"]).ids == resolve(base_spec()).ids

    fields = _probe_specs("probe_default_indicator_fields")
    assert (
        resolve(fields["ema-source-timeframe-omitted"]).ids
        == resolve(fields["ema-source-timeframe-explicit"]).ids
    )
    assert (
        resolve(fields["exit-distance-period-timeframe-omitted"]).ids.exit_policy
        == resolve(fields["exit-distance-period-14-explicit"]).ids.exit_policy
    )
    assert resolve_ema_request({"period": 200}, "p", base_timeframe=BASE_TIMEFRAME) == (
        resolve_ema_request(
            {"period": 200, "source": "close", "timeframe": "base"},
            "p",
            base_timeframe=BASE_TIMEFRAME,
        )
    )


def test_timeframe_alias_resolves_to_the_same_identity() -> None:
    specs = _probe_specs("probe_timeframe_alias")
    base = resolve(specs["stack-base"])
    literal = resolve(specs["stack-5m-literal"])
    # The plan labels differ ('base' vs '5m') -- the identities must not.
    assert base.planned.anchor_columns != literal.planned.anchor_columns
    for role in ("fast", "anchor", "slow"):
        assert (
            base.ids.features[base.planned.anchor_columns[role]]
            == literal.ids.features[literal.planned.anchor_columns[role]]
        )
    assert base.ids.direction_blockers == literal.ids.direction_blockers
    assert base.ids.setups == literal.ids.setups
    assert base.ids.triggers == literal.ids.triggers

    assert (
        resolve(specs["width-atr-base"]).ids.setups
        == resolve(specs["width-atr-5m-literal"]).ids.setups
    )
    assert (
        resolve(specs["width-atr-base"]).ids.exit_policy
        == resolve(specs["exit-distance-5m-literal"]).ids.exit_policy
    )
    rsi_base = resolve(specs["rsi-blocker-base"]).ids.direction_blockers
    rsi_literal = resolve(specs["rsi-blocker-5m-literal"]).ids.direction_blockers
    assert rsi_base == rsi_literal


def test_numeric_spelling_normalizes_to_the_same_identity() -> None:
    specs = _probe_specs("probe_float_normalization")
    tp = [
        resolve(specs[name]).ids.exit_policy
        for name in ("tp-6.75", "tp-6.750", "tp-6.7500000000000001", "tp-string-6.75")
    ]
    assert all(entry == tp[0] for entry in tp)
    assert (
        resolve(specs["tp-int-6"]).ids.exit_policy == resolve(specs["tp-float-6.0"]).ids.exit_policy
    )
    assert (
        resolve(specs["width-current-int-1"]).ids.setups
        == resolve(specs["width-current-float-1.0"]).ids.setups
    )
    assert (
        resolve(specs["untouched-lookback-float-70.0"]).ids.setups
        == resolve(specs["untouched-lookback-int-70"]).ids.setups
    )


def test_declared_order_and_instance_ids_are_labels_only() -> None:
    specs = _probe_specs("probe_rule_order_and_labels")
    original = resolve(specs["exits-original-ids"]).ids.exit_policy
    for name in ("exits-renamed-ids", "exits-tp-declared-first"):
        other = resolve(specs[name]).ids.exit_policy
        assert other.by_profile == original.by_profile
        assert other.select == original.select
    a_then_b = resolve(specs["equal-sl-a-then-b"]).ids.exit_policy
    b_then_a = resolve(specs["equal-sl-b-then-a"]).ids.exit_policy
    assert a_then_b.by_profile == b_then_a.by_profile and a_then_b.select == b_then_a.select

    width_first = resolve(specs["setups-width-then-untouched"]).ids.setups
    untouched_first = resolve(specs["setups-untouched-then-width"]).ids.setups
    renamed = resolve(specs["setups-renamed-instance-ids"]).ids.setups
    for left, right in zip(width_first, untouched_first, strict=True):
        assert left.setups_ok == right.setups_ok
        assert left.pre_trigger_allowed == right.pre_trigger_allowed
    for left, right in zip(width_first, renamed, strict=True):
        assert [setup.local for setup in left.setups] == [setup.local for setup in right.setups]
        assert left.setups_ok == right.setups_ok

    order_a = resolve(specs["blockers-order-a"]).ids.direction_blockers
    order_b = resolve(specs["blockers-order-b"]).ids.direction_blockers
    for left, right in zip(order_a, order_b, strict=True):
        assert left.blockers_ok == right.blockers_ok
        assert left.pre_setup_allowed == right.pre_setup_allowed


def test_side_is_part_of_identity_only_when_read() -> None:
    both = resolve(base_spec())
    width_long, width_short = (_setup(both, "width1", side) for side in ("long", "short"))
    assert width_long.local == width_short.local and width_long.local.side is None
    assert width_long.width_prefix == width_short.width_prefix
    untouched_long, untouched_short = (
        _setup(both, "untouched1", side) for side in ("long", "short")
    )
    assert untouched_long.local != untouched_short.local
    assert {untouched_long.local.side, untouched_short.local.side} == {"long", "short"}
    # Distance exits are side-free; long/short selects over neutral profiles
    # read the same inputs, so they share identities.
    exit_ids = both.ids.exit_policy
    assert all(node.side is None for node in exit_ids.distance_rules.values())
    assert (
        exit_ids.select[("stop_loss_ratio", "long")]
        == exit_ids.select[("stop_loss_ratio", "short")]
    )
    # A side-free node resolved from a long-only spec equals the one from a
    # long+short spec.
    long_only = resolve(_with(base_spec(), "trade_sides", ["long"]))
    assert _setup(long_only, "width1", "long").local == width_long.local


def test_stop_loss_and_take_profit_share_distance_identity_when_computation_matches() -> None:
    spec = _exits(
        base_spec(),
        [_atr_exit("sl", "stop_loss", 3.0), _atr_exit("tp", "take_profit", 3.0)],
    )
    distance_rules = resolve(spec).ids.exit_policy.distance_rules
    assert distance_rules["sl"] == distance_rules["tp"]


# -- (b) distinct computation -> distinct identity -----------------------------------------


def test_source_distinct_ema_never_collides_in_identity() -> None:
    requested = {
        source: resolve_ema_request(
            {"period": 200, "source": source}, "p", base_timeframe=BASE_TIMEFRAME
        )
        for source in ("close", "open", "high", "low")
    }
    assert len(set(requested.values())) == 4

    specs = _probe_specs("probe_source_distinct_same_period")
    anchors = {
        name: (lambda item: item.ids.features[item.planned.anchor_columns["anchor"]])(
            resolve(specs[name])
        )
        for name in (
            "anchor-ema200-close",
            "anchor-ema200-open",
            "anchor-ema200-high",
            "anchor-ema200-close-again",
        )
    }
    assert anchors["anchor-ema200-close"] == anchors["anchor-ema200-close-again"]
    assert len({anchors[name] for name in anchors}) == 3
    # ...and every node reading the anchor inherits the distinction.
    close_ids = resolve(specs["anchor-ema200-close"]).ids
    open_ids = resolve(specs["anchor-ema200-open"]).ids
    assert close_ids.triggers != open_ids.triggers
    assert close_ids.direction_blockers != open_ids.direction_blockers


def test_pinned_within_spec_source_collision_is_preserved_not_fixed() -> None:
    """Legacy feature-plan dedup keys EMAs by a source-blind `output_id`, so
    an open-source context EMA(200) reads the close-source stack EMA(200)
    series (first planned wins) -- pinned in the golden corpus and
    deliberately unchanged. The identity layer reports this truthfully:
    the *requested* open EMA has its own identity, while the context's
    *consumed* upstream is the close EMA it actually reads."""

    specs = _probe_specs("probe_source_distinct_same_period")
    item = resolve(specs["within-spec-context-open-vs-stack-close"])
    stack_anchor_label = item.planned.anchor_columns["anchor"]
    context_anchor_label = item.planned.htf_context_columns_by_ref["htf"]["anchor"]

    # Plan/compute behavior is untouched: one shared label, one close feature.
    assert context_anchor_label == stack_anchor_label
    planned = [f for f in item.planned.indicator_plan.features if f.output_id == stack_anchor_label]
    assert len(planned) == 1 and planned[0].source == "close"

    requested = resolve_context_ema_requests(item.raw_spec, base_timeframe=BASE_TIMEFRAME)["htf"]
    stack_anchor = item.ids.features[stack_anchor_label]
    assert requested["anchor"] != stack_anchor  # sound: open != close
    assert requested["anchor"].param("source") == canonical("open")
    consumed = item.ids.contexts["htf"].dependency("anchor")
    assert consumed == stack_anchor  # truthful: the context reads the close series

    exit_item = resolve(specs["within-spec-exit-ema-open-vs-anchor-close"])
    rule = next(
        rule
        for rule in resolve_exit_rule_groups(exit_item.raw_spec)["always_on"]
        if rule["instance_id"] == "close-loss-open-ema"
    )
    requested_exit_ema = resolve_ema_request(rule["ema"], "p", base_timeframe=BASE_TIMEFRAME)
    signal = exit_item.ids.exit_policy.signal_rules["close-loss-open-ema"]["long"]
    exit_anchor = exit_item.ids.features[exit_item.planned.anchor_columns["anchor"]]
    assert requested_exit_ema != exit_anchor
    assert signal.dependency("ema") == exit_anchor


def test_non_equivalent_timeframe_and_parameters_are_distinct() -> None:
    specs = _probe_specs("probe_timeframe_alias")
    base = resolve(specs["stack-base"])
    htf = resolve(specs["stack-15m-non-equivalent"])
    for role in ("fast", "anchor", "slow"):
        assert (
            base.ids.features[base.planned.anchor_columns[role]]
            != htf.ids.features[htf.planned.anchor_columns[role]]
        )

    defaults = _probe_specs("probe_default_setup_params")
    assert _setup(resolve(defaults["untouched-lookback-49"]), "untouched1", "long").local != (
        _setup(resolve(defaults["untouched-lookback-50-explicit"]), "untouched1", "long").local
    )
    assert _setup(resolve(defaults["width-all-omitted"]), "width1", "long").local != (
        _setup(resolve(defaults["width-minimal-params"]), "width1", "long").local
    )

    components = _probe_specs("probe_default_components")
    touch = resolve(components["trigger-touch-string"]).ids.triggers
    reclaim = resolve(components["trigger-reclaim-string"]).ids.triggers
    strong = resolve(
        _with(base_spec(), "components", "trigger", {"component_id": "strong_reclaim_anchor"})
    ).ids.triggers
    reclaim_2 = resolve(
        _with(
            base_spec(), "components", "trigger", {"component_id": "reclaim_anchor", "lookback": 2}
        )
    ).ids.triggers
    assert len({entry[0].trigger for entry in (touch, reclaim, strong, reclaim_2)}) == 4

    floats = _probe_specs("probe_float_normalization")
    assert resolve(floats["tp-6.75"]).ids.exit_policy != resolve(floats["tp-int-6"]).ids.exit_policy


def test_width_prefix_suffix_split_isolates_threshold_changes() -> None:
    base = resolve(_with(base_spec(), "setups", [_width()]))
    threshold = resolve(_with(base_spec(), "setups", [_width(min_current_width_atr=2.5)]))
    recent = resolve(_with(base_spec(), "setups", [_width(min_recent_width_atr=5.0)]))
    lookback = resolve(_with(base_spec(), "setups", [_width(width_lookback_bars=60)]))
    base_setup = _setup(base, "width1", "long")
    for other in (threshold, recent):
        other_setup = _setup(other, "width1", "long")
        assert other_setup.width_prefix == base_setup.width_prefix  # shared prefix
        assert other_setup.local != base_setup.local  # distinct suffix
    lookback_setup = _setup(lookback, "width1", "long")
    assert lookback_setup.width_prefix != base_setup.width_prefix
    assert lookback_setup.local != base_setup.local


def test_side_reading_nodes_differ_by_side() -> None:
    both = resolve(base_spec()).ids
    long_ids, short_ids = both.direction_blockers
    assert long_ids.direction != short_ids.direction
    assert both.triggers[0].trigger != both.triggers[1].trigger


# -- coincidentally equal outputs -------------------------------------------------------


def test_coincidentally_equal_outputs_keep_distinct_identities() -> None:
    """Two RSI blockers whose lookbacks differ (20 vs 35) but whose threshold
    is unreachable (RSI <= 100 < 150): both compute an all-allowed mask with
    identical traces. Distinct normalized inputs -> distinct identities,
    regardless of the equal outputs."""

    def spec(lookback: int) -> Spec:
        blocker = {**_RSI_BLOCKER, "lookback": lookback, "long_block_above": 150.0}
        return _with(
            _with(base_spec(), "components", "blockers", [blocker]), "trade_sides", ["long"]
        )

    short, long_ = evaluate(spec(20)), evaluate(spec(35))
    short_mask = short.evaluation.direction_blockers[0].blockers[0]
    long_mask = long_.evaluation.direction_blockers[0].blockers[0]
    assert all(short_mask.intrinsic_allowed)
    assert digest((short_mask.intrinsic_allowed, short_mask.trace)) == digest(
        (long_mask.intrinsic_allowed, long_mask.trace)
    )

    short_id = short.ids.direction_blockers[0].blocker_intrinsic[0][1]
    long_id = long_.ids.direction_blockers[0].blocker_intrinsic[0][1]
    assert short_id != long_id
    # The identities differ exactly in the normalized input that differs.
    assert short_id.param("lookback") != long_id.param("lookback")
    assert (short_id.kind, short_id.upstream, short_id.side) == (
        long_id.kind,
        long_id.upstream,
        long_id.side,
    )


# -- (c) same identity -> bit-identical result -------------------------------------------


def test_same_identity_implies_bit_identical_result_across_corpus() -> None:
    """Every node of every corpus spec is keyed by its identity; any identity
    seen more than once (within or across specs) must carry a bit-identical
    computed output every time. Non-vacuous: repeated identities must occur
    in every node family."""

    first_seen: dict[NodeSpec, tuple[str, str]] = {}
    repeats: dict[str, int] = {}
    evaluated = _evaluated_corpus()
    assert len(evaluated) > 100
    for name, item in evaluated:
        for address, node, output in node_outputs(item):
            seen = first_seen.get(node)
            if seen is None:
                first_seen[node] = (f"{name}:{address}", output)
                continue
            assert output == seen[1], (
                f"identity collision with different results: {seen[0]} vs {name}:{address}\n{node}"
            )
            family = node.kind.split(".")[0]
            repeats[family] = repeats.get(family, 0) + 1
    for family in (
        "indicator",
        "context",
        "context_consumption",
        "direction",
        "blocker",
        "mask",
        "setup",
        "trigger",
        "exit",
    ):
        assert repeats.get(family, 0) > 0, f"no repeated identity exercised for {family}"


def test_equivalent_pairs_compute_bit_identical_results() -> None:
    """The (a) pairs, checked for the consequence required by (c)."""

    pairs = [
        (
            "probe_default_setup_params",
            "untouched-lookback-omitted",
            "untouched-lookback-50-explicit",
        ),
        ("probe_default_setup_params", "width-minimal-params", "width-explicit-defaults"),
        ("probe_timeframe_alias", "stack-base", "stack-5m-literal"),
        ("probe_float_normalization", "tp-6.75", "tp-string-6.75"),
        ("probe_rule_order_and_labels", "equal-sl-a-then-b", "equal-sl-b-then-a"),
    ]
    for case_name, left_name, right_name in pairs:
        specs = _probe_specs(case_name)
        left = {node: output for _, node, output in node_outputs(evaluate(specs[left_name]))}
        right = {node: output for _, node, output in node_outputs(evaluate(specs[right_name]))}
        shared = left.keys() & right.keys()
        assert shared, (case_name, left_name, right_name)
        for node in shared:
            assert left[node] == right[node], (case_name, left_name, right_name, node)


def test_order_insensitive_aggregates_are_bitwise_permutation_invariant() -> None:
    """The exit aggregates' set-valued upstream assumes the reductions are
    exactly commutative and idempotent -- including the signed-zero and NaN
    corner cases `_min` (pandas row-wise NaN-skipping min) could expose."""

    index = pd.RangeIndex(4)
    columns = [
        pd.Series([0.0, math.nan, 1.0, -0.0], index=index),
        pd.Series([-0.0, 2.0, math.nan, 0.0], index=index),
        pd.Series([math.nan, math.nan, 1.0, 0.0], index=index),
        pd.Series([0.5, -1.0, 1.0, -0.0], index=index),
    ]
    reference = exits_module._min(columns, index).to_numpy().tobytes()
    for size in range(1, len(columns) + 1):
        for chosen in itertools.combinations(range(len(columns)), size):
            base = exits_module._min([columns[i] for i in chosen], index).to_numpy().tobytes()
            duplicated = [columns[i] for i in chosen] + [columns[chosen[0]]]
            for order in itertools.permutations(duplicated):
                assert exits_module._min(list(order), index).to_numpy().tobytes() == base
    assert reference  # full-set result exercised
    bools = [pd.Series(v, index=index) for v in ([True, False, False, True], [False] * 4)]
    for order in itertools.permutations(bools + bools[:1]):
        assert np.array_equal(
            exits_module._or(list(order), index).to_numpy(),
            exits_module._or(bools, index).to_numpy(),
        )
