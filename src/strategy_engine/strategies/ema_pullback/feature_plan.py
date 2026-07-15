"""BBB-compatible FeaturePlan construction from canonical ema_pullback specs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature

_ALLOWED_KINDS = {"ema", "atr", "atr_distance", "rsi", "adx", "di_plus", "di_minus"}


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
    return value


def _ema_id(timeframe: str, period: int) -> str:
    return f"ema_close_{timeframe}_{period}"


def _atr_id(timeframe: str, period: int) -> str:
    return f"atr_close_{timeframe}_{period}"


def _rsi_id(timeframe: str, period: int) -> str:
    return f"rsi_close_{timeframe}_{period}"


def _adx_id(kind: str, timeframe: str, period: int) -> str:
    return f"{kind}_close_{timeframe}_{period}"


def _multiplier_token(multiplier: float) -> str:
    return str(float(multiplier)).replace(".", "_")


def _ema(raw: Any, path: str) -> tuple[str, str, int]:
    payload = _mapping(raw, path)
    source = str(payload.get("source", "close"))
    timeframe = str(payload.get("timeframe", "base"))
    period = _positive_int(payload.get("period"), f"{path}.period")
    return source, timeframe, period


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
    exit_policy = _mapping(trade_management.get("exit_policy"), "trade_management.exit_policy")

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
        output_id = _ema_id(timeframe, period)
        add(PlannedFeature(output_id, "ema", timeframe, source, {"period": period}))
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
        timeframe = str(provider.get("timeframe", ""))
        source = str(provider.get("source", "close"))
        resolved: dict[str, str] = {}
        for role in ("fast", "anchor", "slow"):
            period = _positive_int(
                provider.get(f"{role}_period"), f"contexts.{context_ref}.{role}_period"
            )
            output_id = _ema_id(timeframe, period)
            add(PlannedFeature(output_id, "ema", timeframe, source, {"period": period}))
            resolved[role] = output_id
        htf_columns[str(context_ref)] = resolved

    all_exits: list[Mapping[str, Any]] = []
    always_on = _mapping(exit_policy.get("always_on"), "exit_policy.always_on")
    all_exits.extend(
        _mapping(item, "exit") for item in _sequence(always_on.get("exits"), "always_on.exits")
    )
    profiles = _mapping(exit_policy.get("profiles"), "exit_policy.profiles")
    for profile_name in ("aligned", "countertrend", "neutral"):
        profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")
        all_exits.extend(
            _mapping(item, f"profiles.{profile_name}.exits[]")
            for item in _sequence(profile.get("exits"), f"profiles.{profile_name}.exits")
        )

    exit_columns: dict[str, str] = {}
    ema_columns: dict[tuple[str, int], str] = {}
    setup_columns: dict[str, dict[str, str]] = {}
    setups = _sequence(root.get("setups"), "setups")
    for index, setup_raw in enumerate(setups):
        setup = _mapping(setup_raw, f"setups[{index}]")
        params = _mapping(setup.get("params", {}), f"setups[{index}].params")
        component_id = str(setup.get("component_id", ""))
        instance_id = str(setup.get("instance_id", ""))
        if component_id == "anchor_stack_width_setup":
            timeframe = str(params.get("atr_timeframe", "base"))
            period = _positive_int(
                params.get("atr_period", 14), f"setups[{index}].params.atr_period"
            )
            setup_columns[instance_id] = {
                "fast": fast,
                "anchor": anchor,
                "slow": slow,
                "atr": add_atr(timeframe, period),
            }
        elif component_id == "ema_bounce_counter_setup":
            setup_columns[instance_id] = {"fast": fast, "anchor": anchor, "slow": slow}

    rsi_columns: dict[tuple[str, int], str] = {}
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]] = {}

    for index, rule in enumerate(all_exits):
        distance = rule.get("distance")
        if distance is None:
            continue
        payload = _mapping(distance, f"exits[{index}].distance")
        timeframe = str(payload.get("timeframe", "base"))
        period = _positive_int(payload.get("period", 14), f"exits[{index}].distance.period")
        multiplier = float(payload.get("multiplier"))
        base_id = add_atr(timeframe, period)
        distance_id = f"{base_id}_x{_multiplier_token(multiplier)}"
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
        instance_id = str(rule.get("instance_id", ""))
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
