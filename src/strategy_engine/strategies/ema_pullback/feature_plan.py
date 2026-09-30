"""BBB-compatible FeaturePlan construction from canonical ema_pullback specs."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.feature_kinds import feature_kind, feature_kinds
from strategy_engine.indicators.implementations.range_evaluator import (
    resolve_feature,
    resolve_indicator_plan,
)
from strategy_engine.strategies.ema_pullback.composite_spec import (
    COMPOSITE_SETUP,
    child_setup_item,
    parse_composite_setup,
)
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    require_non_empty_instance_id,
    resolve_exit_rule_groups,
)

_ALLOWED_KINDS = frozenset(contract.kind for contract in feature_kinds())


@dataclass(frozen=True, slots=True)
class EmaPullbackFeaturePlan:
    indicator_plan: IndicatorPlan
    anchor_columns: dict[str, str]
    exit_distance_columns: dict[str, str]
    rsi_columns: dict[tuple[str, int], str]
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]] = field(default_factory=dict)
    setup_columns_by_instance_id: dict[str, dict[str, str]] = field(default_factory=dict)
    ema_columns: dict[tuple[str, int], str] = field(default_factory=dict)
    htf_context_columns_by_ref: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_wire(self) -> dict[str, object]:
        return {
            "plan_version": self.indicator_plan.plan_version,
            "plan_hash": self.indicator_plan.plan_hash,
            "features": [feature.canonical_payload() for feature in self.indicator_plan.features],
            "anchor_columns": self.anchor_columns,
            "exit_distance_columns": self.exit_distance_columns,
            "rsi_columns": {
                f"{timeframe}:{period}": output_id
                for (timeframe, period), output_id in self.rsi_columns.items()
            },
            "adx_dmi_columns": {
                f"{timeframe}:{period}": columns
                for (timeframe, period), columns in self.adx_dmi_columns.items()
            },
            "setup_columns_by_instance_id": self.setup_columns_by_instance_id,
            "ema_columns": {
                f"{timeframe}:{period}": output_id
                for (timeframe, period), output_id in self.ema_columns.items()
            },
            "htf_context_columns_by_ref": self.htf_context_columns_by_ref,
        }


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(value)


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError(f"{path} must be a positive integer")
    return cast(int, value)


def _label(kind: str, timeframe: str, period: int) -> str:
    return feature_kind(kind).label(timeframe, "close", {"period": period}, ())


def _ema_id(timeframe: str, period: int) -> str:
    return _label("ema", timeframe, period)


def _atr_id(timeframe: str, period: int) -> str:
    return _label("atr", timeframe, period)


def _rsi_id(timeframe: str, period: int) -> str:
    return _label("rsi", timeframe, period)


def _adx_id(kind: str, timeframe: str, period: int) -> str:
    return _label(kind, timeframe, period)


def _ema(raw: Any, path: str) -> tuple[str, str, int]:
    payload = _mapping(raw, path)
    source = str(payload.get("source", "close"))
    timeframe = str(payload.get("timeframe", "base"))
    period = _positive_int(payload.get("period"), f"{path}.period")
    return source, timeframe, period


def _ema_feature(source: str, timeframe: str, period: int) -> PlannedFeature:
    """The planned EMA feature for one normalized EMA request. Its
    `output_id` deliberately keeps today's source-blind `_ema_id` label
    (pinned legacy behavior: same timeframe/period, different source,
    collide in plan deduplication and the first-planned one wins)."""

    return PlannedFeature(_ema_id(timeframe, period), "ema", timeframe, source, {"period": period})


def _context_ema_features(
    context_ref: object, provider: Mapping[str, Any]
) -> Iterator[tuple[str, PlannedFeature]]:
    """The fast/anchor/slow EMA features one HTF context provider requests
    (lazy, role order, so validation interleaves with planning exactly as
    before)."""

    timeframe = str(provider.get("timeframe", ""))
    source = str(provider.get("source", "close"))
    for role in ("fast", "anchor", "slow"):
        period = _positive_int(
            provider.get(f"{role}_period"), f"contexts.{context_ref}.{role}_period"
        )
        yield role, _ema_feature(source, timeframe, period)


def _rsi(raw: Any, path: str) -> tuple[str, int] | None:
    if raw is None:
        return None
    payload = _mapping(raw, path)
    return str(payload.get("timeframe", "base")), _positive_int(
        payload.get("period", 14), f"{path}.period"
    )


def build_feature_plan_from_canonical_spec(raw_spec: Mapping[str, Any]) -> EmaPullbackFeaturePlan:
    """Build the BBB v1 plan from ``strategy_spec_to_dict`` wire shape."""

    root = _mapping(raw_spec, "raw_spec")
    stack = _mapping(root.get("anchor_stack"), "anchor_stack")
    components = _mapping(root.get("components"), "components")
    trade_management = _mapping(root.get("trade_management"), "trade_management")

    features: list[PlannedFeature] = []
    seen: set[str] = set()

    def add(feature: PlannedFeature) -> None:
        if feature.kind not in _ALLOWED_KINDS:
            raise InvalidRequestError("unsupported planned feature kind", kind=feature.kind)
        if feature.output_id in seen:
            return
        seen.add(feature.output_id)
        features.append(feature)

    def add_ema(raw: Any, path: str, ema_columns: dict[tuple[str, int], str] | None = None) -> str:
        source, timeframe, period = _ema(raw, path)
        feature = _ema_feature(source, timeframe, period)
        output_id = feature.output_id
        add(feature)
        if ema_columns is not None:
            ema_columns[(timeframe, period)] = output_id
        return output_id

    def add_atr(timeframe: str, period: int) -> str:
        output_id = _atr_id(timeframe, period)
        add(PlannedFeature(output_id, "atr", timeframe, "close", {"period": period}))
        return output_id

    def add_rsi(timeframe: str, period: int, columns: dict[tuple[str, int], str]) -> str:
        output_id = _rsi_id(timeframe, period)
        add(PlannedFeature(output_id, "rsi", timeframe, "close", {"period": period}))
        columns[(timeframe, period)] = output_id
        return output_id

    def add_adx_dmi(
        timeframe: str,
        period: int,
        columns: dict[tuple[str, int], dict[str, str]],
    ) -> None:
        key = (timeframe, period)
        if key in columns:
            return
        resolved: dict[str, str] = {}
        for kind in ("adx", "di_plus", "di_minus"):
            output_id = _adx_id(kind, timeframe, period)
            add(PlannedFeature(output_id, kind, timeframe, "close", {"period": period}))
            resolved[kind] = output_id
        columns[key] = resolved

    fast = add_ema(stack.get("fast"), "anchor_stack.fast")
    anchor = add_ema(stack.get("anchor"), "anchor_stack.anchor")
    slow = add_ema(stack.get("slow"), "anchor_stack.slow")

    htf_columns: dict[str, dict[str, str]] = {}
    contexts_raw = root.get("contexts", {})
    contexts = _mapping(contexts_raw, "contexts") if contexts_raw is not None else {}
    for context_ref, provider_raw in contexts.items():
        provider = _mapping(provider_raw, f"contexts.{context_ref}")
        resolved: dict[str, str] = {}
        for role, feature in _context_ema_features(context_ref, provider):
            add(feature)
            resolved[role] = feature.output_id
        htf_columns[str(context_ref)] = resolved

    exit_rule_groups = resolve_exit_rule_groups(root)
    all_exits: list[Mapping[str, Any]] = [
        rule
        for group in ("always_on", "aligned", "countertrend", "neutral")
        for rule in exit_rule_groups[group]
    ]

    exit_columns: dict[str, str] = {}
    ema_columns: dict[tuple[str, int], str] = {}
    setup_columns: dict[str, dict[str, str]] = {}

    def plan_setup_columns(
        component_id: str, instance_id: str, params: Mapping[str, Any], path: str
    ) -> None:
        if component_id == "anchor_stack_width_setup":
            timeframe = str(params.get("atr_timeframe", "base"))
            period = _positive_int(params.get("atr_period", 14), f"{path}.params.atr_period")
            setup_columns[instance_id] = {
                "fast": fast,
                "anchor": anchor,
                "slow": slow,
                "atr": add_atr(timeframe, period),
            }
        elif component_id == "ema_bounce_counter_setup":
            setup_columns[instance_id] = {"fast": fast, "anchor": anchor, "slow": slow}

    # Predicate feature operands are planned after every existing consumer
    # (design D6/D7): a predicate never takes over a label an existing
    # consumer would have planned, and fails closed when the label it asks
    # for already holds a different feature.
    predicate_features: list[PlannedFeature] = []
    setups = _sequence(root.get("setups"), "setups")
    for index, setup_raw in enumerate(setups):
        setup = _mapping(setup_raw, f"setups[{index}]")
        params = _mapping(setup.get("params", {}), f"setups[{index}].params")
        component_id = str(setup.get("component_id", ""))
        instance_id = str(setup.get("instance_id", ""))
        if component_id == COMPOSITE_SETUP:
            composite = parse_composite_setup(setup, f"setups[{index}]")
            for child_index, child in enumerate(composite.children):
                if child.predicate is not None:
                    predicate_features.extend(
                        parse_predicate(
                            child.predicate,
                            f"setups[{index}].params.children[{child_index}].predicate",
                            context_refs=htf_columns,
                        ).features()
                    )
                    continue
                child_item = child_setup_item(composite, child)
                plan_setup_columns(
                    child_item["component_id"],
                    child_item["instance_id"],
                    child_item["params"],
                    f"setups[{index}].params.children[{child_index}].setup",
                )
        else:
            plan_setup_columns(component_id, instance_id, params, f"setups[{index}]")

    rsi_columns: dict[tuple[str, int], str] = {}
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]] = {}

    for index, rule in enumerate(all_exits):
        require_non_empty_instance_id(rule.get("instance_id"), f"exits[{index}].instance_id")
        distance = rule.get("distance")
        if distance is None:
            continue
        payload = _mapping(distance, f"exits[{index}].distance")
        timeframe = str(payload.get("timeframe", "base"))
        period = _positive_int(payload.get("period", 14), f"exits[{index}].distance.period")
        multiplier = float(cast(int | float | str, payload.get("multiplier")))
        base_id = add_atr(timeframe, period)
        distance_id = feature_kind("atr_distance").label(
            timeframe, None, {"multiplier": multiplier}, (base_id,)
        )
        add(
            PlannedFeature(
                distance_id,
                "atr_distance",
                timeframe,
                None,
                {"multiplier": multiplier},
                (base_id,),
            )
        )
        instance_id = str(rule.get("instance_id"))
        exit_kind = str(rule.get("exit_kind", ""))
        exit_columns[instance_id] = distance_id
        exit_columns.setdefault(exit_kind, distance_id)

    rsi_specs: list[tuple[str, int]] = []
    blockers = _sequence(components.get("blockers"), "components.blockers")
    for index, blocker_raw in enumerate(blockers):
        blocker = _mapping(blocker_raw, f"components.blockers[{index}]")
        rsi = _rsi(blocker.get("rsi"), f"components.blockers[{index}].rsi")
        if rsi is not None:
            rsi_specs.append(rsi)
        trend = blocker.get("trend_strength")
        if trend is not None:
            payload = _mapping(trend, f"components.blockers[{index}].trend_strength")
            add_adx_dmi(
                str(payload.get("timeframe", "base")),
                _positive_int(payload.get("adx_period", 14), "trend_strength.adx_period"),
                adx_dmi_columns,
            )

    for index, rule in enumerate(all_exits):
        rsi = _rsi(rule.get("rsi"), f"exits[{index}].rsi")
        if rsi is not None:
            rsi_specs.append(rsi)
        for field_name in ("ema", "fast_ema", "slow_ema"):
            if rule.get(field_name) is not None:
                add_ema(
                    rule[field_name],
                    f"exits[{index}].{field_name}",
                    ema_columns,
                )

    for timeframe, period in rsi_specs:
        add_rsi(timeframe, period, rsi_columns)

    exit_management = _mapping(
        trade_management.get("exit_management", {}), "trade_management.exit_management"
    )
    for index, phase_rule_raw in enumerate(exit_management.get("phase_rules", ()) or ()):
        phase_rule = _mapping(phase_rule_raw, f"phase_rules[{index}]")
        condition = _mapping(phase_rule.get("condition"), f"phase_rules[{index}].condition")
        component_id = str(condition.get("component_id", ""))
        params = _mapping(condition.get("params", {}), f"phase_rules[{index}].condition.params")
        if component_id == "mfe_atr":
            atr = _mapping(params.get("atr"), f"phase_rules[{index}].condition.params.atr")
            add_atr(
                str(atr.get("timeframe", "base")),
                _positive_int(atr.get("period"), "phase_rule.atr.period"),
            )
        elif component_id == "adx_di_threshold":
            add_adx_dmi(
                str(params.get("timeframe", "base")),
                _positive_int(params.get("period"), "phase_rule.period"),
                adx_dmi_columns,
            )

    for index, stop_raw in enumerate(exit_management.get("stop_management", ()) or ()):
        stop = _mapping(stop_raw, f"stop_management[{index}]")
        params = _mapping(stop.get("params", {}), f"stop_management[{index}].params")
        component_id = str(stop.get("component_id", ""))
        if (
            component_id == "lock_profit_stop"
            or component_id == "break_even_stop"
            and params.get("buffer_type") == "atr"
        ):
            atr = _mapping(params.get("atr", {}), f"stop_management[{index}].params.atr")
            add_atr(
                str(atr.get("timeframe", "base")),
                _positive_int(
                    atr.get("period", params.get("atr_period", 14)),
                    f"stop_management[{index}].params.atr_period",
                ),
            )

    for index, runtime_raw in enumerate(exit_management.get("runtime_exits", ()) or ()):
        runtime = _mapping(runtime_raw, f"runtime_exits[{index}]")
        params = _mapping(runtime.get("params", {}), f"runtime_exits[{index}].params")
        component_id = str(runtime.get("component_id", ""))
        if component_id == "rsi_signal_exit":
            rsi = _rsi(params.get("rsi"), f"runtime_exits[{index}].params.rsi")
            if rsi is not None:
                add_rsi(*rsi, rsi_columns)
        elif component_id == "ema_cross_loss_exit":
            for field_name in ("fast_ema", "slow_ema"):
                add_ema(
                    params.get(field_name),
                    f"runtime_exits[{index}].params.{field_name}",
                    ema_columns,
                )

    if predicate_features:
        planned_by_label = {feature.output_id: feature for feature in features}
        for feature in predicate_features:
            existing = planned_by_label.get(feature.output_id)
            if existing is not None and existing != feature:
                raise InvalidRequestError(
                    "predicate feature collides with a different planned feature",
                    output_id=feature.output_id,
                )
            add(feature)
            planned_by_label[feature.output_id] = feature

    return EmaPullbackFeaturePlan(
        indicator_plan=IndicatorPlan("bbb_v1", tuple(features)),
        anchor_columns={"fast": fast, "anchor": anchor, "slow": slow},
        exit_distance_columns=exit_columns,
        rsi_columns=rsi_columns,
        adx_dmi_columns=adx_dmi_columns,
        setup_columns_by_instance_id=setup_columns,
        ema_columns=ema_columns,
        htf_context_columns_by_ref=htf_columns,
    )


# -- semantic node identity (batch-computation-reuse group 3) -----------------


def resolve_feature_identities(
    planned: EmaPullbackFeaturePlan, *, base_timeframe: str
) -> dict[str, NodeSpec]:
    """Plan column label -> identity of the computation that fills it.

    Downstream nodes read indicator values by plan column label, so their
    upstream identity is whatever this map holds for the label they read --
    the identity of what is *actually computed and consumed*, never the
    label itself. For the pinned legacy source collision (e.g. an open-source
    context EMA(200) whose `ema_close_base_200` label was already taken by
    the close-source stack anchor) the label resolves to the close EMA's
    identity, which is exactly the series that consumer reads today.
    """

    return resolve_indicator_plan(planned.indicator_plan, base_timeframe=base_timeframe)


def resolve_ema_request(raw: Any, path: str, *, base_timeframe: str) -> NodeSpec:
    """Identity of the EMA an `{source?, timeframe?, period}` fragment
    *requests*, normalized through the same `_ema` defaults the plan builder
    applies. Source-aware: close vs open EMA with the same timeframe/period
    get distinct identities even though their plan labels collide."""

    source, timeframe, period = _ema(raw, path)
    return resolve_feature(
        _ema_feature(source, timeframe, period), base_timeframe=base_timeframe, upstream={}
    )


def resolve_context_ema_requests(
    raw_spec: Mapping[str, Any], *, base_timeframe: str
) -> dict[str, dict[str, NodeSpec]]:
    """Identity of each HTF context's *requested* fast/anchor/slow EMA
    (`context_ref -> role -> identity`), with the plan builder's context
    defaults (source "close", timeframe "")."""

    contexts_raw = raw_spec.get("contexts", {})
    contexts = _mapping(contexts_raw, "contexts") if contexts_raw is not None else {}
    requested: dict[str, dict[str, NodeSpec]] = {}
    for context_ref, provider_raw in contexts.items():
        provider = _mapping(provider_raw, f"contexts.{context_ref}")
        requested[str(context_ref)] = {
            role: resolve_feature(feature, base_timeframe=base_timeframe, upstream={})
            for role, feature in _context_ema_features(context_ref, provider)
        }
    return requested
