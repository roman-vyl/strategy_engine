"""Family-local parser for external ema_pullback strategy instances."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from research.strategies.ema_pullback import component_builders as builders
from research.strategies.ema_pullback.components.registry import (
    ATR_STOP_LOSS_COMPONENT,
    ATR_TAKE_PROFIT_COMPONENT,
    CONSTANT_USD_STOP_LOSS_COMPONENT,
    CONSTANT_USD_TAKE_PROFIT_COMPONENT,
    COUNTER_CANDLE_BLOCKER_COMPONENT,
    EMA_ANCHOR_STACK_TREND_COMPONENT,
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    NO_BLOCKERS_COMPONENT,
    NO_RISK_FILTER_COMPONENT,
    NO_SIGNAL_EXIT_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
    RECLAIM_ANCHOR_COMPONENT,
    STRONG_RECLAIM_ANCHOR_COMPONENT,
    RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
    TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT,
    EMA_CLOSE_LOSS_EXIT_COMPONENT,
    EMA_CROSS_LOSS_EXIT_COMPONENT,
    RSI_SIGNAL_EXIT_COMPONENT,
    TOUCH_ANCHOR_COMPONENT,
    resolve_component,
)
from research.strategies.ema_pullback.context.consumption_validation import (
    validate_htf_regime_gate_params,
)
from research.strategies.ema_pullback.context.policies import (
    EXIT_PROFILE_BY_HTF_STATE_POLICY,
    HTF_REGIME_GATE_POLICY,
)
from research.strategies.ema_pullback.spec import (
    BlockerRuleSpec,
    BreakEvenStopParamsSpec,
    ContextConsumptionPolicySpec,
    ContextConsumptionSpec,
    ContextProviderSpec,
    EmaSpec,
    EmaPullbackStrategySpec,
    ExitPolicySpec,
    ExitPolicyProfilesSpec,
    ExitPolicyGroupSpec,
    ExitManagementSpec,
    LEGACY_EXIT_MANAGEMENT_SHAPE_ERROR,
    LockProfitStopParamsSpec,
    ManagementActivateWhenSpec,
    ManagementAtrRefSpec,
    PhaseRuleConditionSpec,
    PhaseRuleSpec,
    PHASE_RUNTIME_EXIT_PRICES,
    EmaCrossRuntimeExitParamsSpec,
    PhaseRuntimeExitParamsSpec,
    RsiRuntimeExitParamsSpec,
    RUNTIME_EXIT_COMPONENT_IDS,
    RUNTIME_EXIT_KINDS,
    RUNTIME_EXIT_ROLE,
    RuntimeExitRuleSpec,
    STOP_MANAGEMENT_COMPONENT_IDS,
    TRADE_MANAGEMENT_PHASES,
    StopManagementRuleSpec,
    TakeManagementRuleSpec,
    TakeProfileSwitchParamsSpec,
    TradeManagementSpec,
    empty_exit_management,
    ExitRuleSpec,
    SetupRuleSpec,
    SetupSpec,
    TradeSide,
    UntouchedAnchorSetupSpec,
    strategy_spec_config_id,
)
from research.strategies.ema_pullback.spec_instances import (
    make_ema_pullback_strategy_spec,
)


class EmaPullbackInstanceValidationError(ValueError):
    """Raised when a single ema_pullback instance is invalid."""


@dataclass(frozen=True)
class LoadedEmaPullbackInstance:
    spec: EmaPullbackStrategySpec
    strategy_spec_config_id: str


_INSTANCE_FIELDS = frozenset(
    {
        "instance_id",
        "variant",
        "market",
        "strategy",
    }
)

_STRATEGY_FIELDS = frozenset(
    {
        "trade_sides",
        "anchor_stack",
        "direction",
        "setups",
        "trigger",
        "blockers",
        "risk",
        "trade_management",
        "contexts",
    }
)


def load_ema_pullback_config_entry(instance: Mapping[str, Any]) -> LoadedEmaPullbackInstance:
    spec = load_ema_pullback_instance(instance)
    return LoadedEmaPullbackInstance(
        spec=spec,
        strategy_spec_config_id=strategy_spec_config_id(spec),
    )


def load_ema_pullback_instance(instance: Mapping[str, Any]) -> EmaPullbackStrategySpec:
    payload = _require_mapping("ema_pullback instance", instance)
    _reject_unknown_fields("ema_pullback instance", payload, _INSTANCE_FIELDS)
    for key in _INSTANCE_FIELDS - {"variant"}:
        _require_present(payload, key)

    instance_id = _require_non_empty_str(payload, "instance_id")
    if "external_config_id" in payload:
        raise EmaPullbackInstanceValidationError("external_config_id is not supported; use instance_id")

    market = _parse_market(payload["market"])
    strategy = _parse_strategy(payload["strategy"])
    anchor_stack = _parse_anchor_stack(strategy["anchor_stack"])
    direction = _parse_direction(strategy["direction"])
    setups = _parse_setups(strategy["setups"], anchor_stack=anchor_stack)
    trigger = _parse_trigger(strategy["trigger"])
    blockers = _parse_blockers(strategy["blockers"])
    risk = _parse_risk(strategy["risk"])
    trade_management_spec = _parse_trade_management(strategy["trade_management"])
    contexts = _parse_contexts(strategy.get("contexts", {}))

    components = builders.component_stack(
        direction=direction,
        blockers=blockers,
        trigger=trigger,
        risk=risk,
    )
    variant = _optional_non_empty_str(payload, "variant", default="")
    spec = make_ema_pullback_strategy_spec(
        variant=variant if variant else None,
        symbol=market["symbol"],
        base_timeframe=market["base_timeframe"],
        fast_period=anchor_stack["fast"],
        anchor_period=anchor_stack["anchor"],
        slow_period=anchor_stack["slow"],
        anchor_source=anchor_stack["source"],
        anchor_timeframe=anchor_stack["timeframe"],
        enabled_sides=_parse_trade_sides(strategy["trade_sides"]),
        components=components,
        setups=setups,
        trade_management_spec=trade_management_spec,
        contexts=contexts,
    )
    return spec


def _parse_contexts(value: Any) -> tuple[tuple[str, ContextProviderSpec], ...]:
    payload = _require_mapping("strategy.contexts", value if value is not None else {})
    if not payload:
        return ()
    providers: list[tuple[str, ContextProviderSpec]] = []
    for context_ref, provider_raw in payload.items():
        if not isinstance(context_ref, str) or not context_ref.strip():
            raise EmaPullbackInstanceValidationError("strategy.contexts keys must be non-empty strings")
        path = f"strategy.contexts.{context_ref}"
        provider_payload = _require_mapping(path, provider_raw)
        _reject_unknown_fields(
            path,
            provider_payload,
            {"component_id", "timeframe", "source", "fast_period", "anchor_period", "slow_period"},
        )
        providers.append(
            (
                context_ref,
                ContextProviderSpec(
                    component_id=_require_non_empty_str(provider_payload, "component_id"),
                    timeframe=_require_non_empty_str(provider_payload, "timeframe"),
                    source=_optional_non_empty_str(provider_payload, "source", default="close"),
                    fast_period=_require_positive_int(provider_payload, "fast_period"),
                    anchor_period=_require_positive_int(provider_payload, "anchor_period"),
                    slow_period=_require_positive_int(provider_payload, "slow_period"),
                ),
            )
        )
    return tuple(providers)


def _parse_market(value: Any) -> dict[str, str]:
    payload = _require_mapping("market", value)
    _reject_unknown_fields("market", payload, {"symbol", "base_timeframe"})
    return {
        "symbol": _require_non_empty_str(payload, "symbol").upper(),
        "base_timeframe": _require_non_empty_str(payload, "base_timeframe"),
    }


def _parse_strategy(value: Any) -> Mapping[str, Any]:
    payload = _require_mapping("strategy", value)
    if "exits" in payload:
        raise EmaPullbackInstanceValidationError(
            "strategy.exits is no longer supported; use strategy.trade_management.exit_policy"
        )
    _migrate_legacy_setup_to_setups(payload)
    _reject_unknown_fields("strategy", payload, _STRATEGY_FIELDS)
    required = _STRATEGY_FIELDS - {"contexts"}
    for key in required:
        _require_present(payload, key)
    return payload


def _parse_trade_management(value: Any) -> TradeManagementSpec:
    payload = _require_mapping("trade_management", value)
    _reject_unknown_fields("trade_management", payload, {"exit_policy", "exit_management"})
    exit_policy_payload = _require_mapping(
        "trade_management.exit_policy",
        _require_present(payload, "exit_policy"),
    )
    if "context" in exit_policy_payload:
        raise EmaPullbackInstanceValidationError(
            "trade_management.exit_policy.context is no longer supported; "
            "use strategy.contexts and trade_management.exit_policy.context_consumption"
        )
    _reject_unknown_fields(
        "trade_management.exit_policy",
        exit_policy_payload,
        {"context_consumption", "always_on", "profiles"},
    )
    context_consumption = _parse_context_consumption(
        exit_policy_payload.get("context_consumption"),
        path="trade_management.exit_policy.context_consumption",
        allowed_policy_ids=(EXIT_PROFILE_BY_HTF_STATE_POLICY,),
    )
    always_on = _parse_exit_policy_group(
        _require_present(exit_policy_payload, "always_on"),
        path="trade_management.exit_policy.always_on",
    )
    profiles_payload = _require_mapping(
        "trade_management.exit_policy.profiles",
        _require_present(exit_policy_payload, "profiles"),
    )
    _reject_unknown_fields(
        "trade_management.exit_policy.profiles",
        profiles_payload,
        {"aligned", "countertrend", "neutral"},
    )
    profiles = ExitPolicyProfilesSpec(
        aligned=_parse_exit_policy_group(
            _require_present(profiles_payload, "aligned"),
            path="trade_management.exit_policy.profiles.aligned",
        ),
        countertrend=_parse_exit_policy_group(
            _require_present(profiles_payload, "countertrend"),
            path="trade_management.exit_policy.profiles.countertrend",
        ),
        neutral=_parse_exit_policy_group(
            _require_present(profiles_payload, "neutral"),
            path="trade_management.exit_policy.profiles.neutral",
        ),
    )
    _validate_profile_exits_require_consumption(profiles, context_consumption)
    exit_management = empty_exit_management()
    if "exit_management" in payload:
        exit_management = _parse_exit_management(payload["exit_management"])
    return TradeManagementSpec(
        exit_policy=ExitPolicySpec(
            always_on=always_on,
            profiles=profiles,
            context_consumption=context_consumption,
        ),
        exit_management=exit_management,
    )


def _parse_exit_management(value: Any) -> ExitManagementSpec:
    payload = _require_mapping("trade_management.exit_management", value)
    if "always_on" in payload or "profiles" in payload:
        raise EmaPullbackInstanceValidationError(LEGACY_EXIT_MANAGEMENT_SHAPE_ERROR)
    _reject_unknown_fields(
        "trade_management.exit_management",
        payload,
        {
            "mode",
            "phase_rules",
            "stop_management",
            "take_management",
            "runtime_exits",
        },
    )

    mode = _parse_exit_management_mode(payload.get("mode"))

    try:
        return ExitManagementSpec(
            mode=mode,
            phase_rules=_parse_phase_rules(payload.get("phase_rules")),
            stop_management=_parse_stop_management_rules(
                payload.get("stop_management"),
            ),
            take_management=_parse_take_management_rules(
                payload.get("take_management"),
            ),
            runtime_exits=_parse_runtime_exit_rules(
                payload.get("runtime_exits"),
            ),
        )
    except ValueError as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_exit_management_mode(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EmaPullbackInstanceValidationError(
            "trade_management.exit_management.mode must be a non-empty string"
        )
    if value not in ("diagnostic_only", "managed"):
        raise EmaPullbackInstanceValidationError(
            "trade_management.exit_management.mode must be 'diagnostic_only' or 'managed'"
        )
    return value


def _parse_phase_rules(value: Any) -> tuple[PhaseRuleSpec, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise EmaPullbackInstanceValidationError(
            "trade_management.exit_management.phase_rules must be a list"
        )
    out: list[PhaseRuleSpec] = []
    for i, item in enumerate(value):
        out.append(
            _parse_phase_rule(
                item,
                path=f"trade_management.exit_management.phase_rules[{i}]",
            )
        )
    return tuple(out)


def _parse_phase_rule(value: Any, *, path: str) -> PhaseRuleSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"rule_id", "to_phase", "condition"})
    try:
        return PhaseRuleSpec(
            rule_id=_require_non_empty_str(payload, "rule_id"),
            to_phase=_require_non_empty_str(payload, "to_phase"),  # type: ignore[arg-type]
            condition=_parse_phase_rule_condition(
                _require_present(payload, "condition"),
                path=f"{path}.condition",
            ),
        )
    except ValueError as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_phase_rule_condition(value: Any, *, path: str) -> PhaseRuleConditionSpec:
    from research.strategies.ema_pullback.phase_rule_conditions.registry import (
        LEGACY_PHASE_CONDITION_TYPE_ERROR,
        parse_phase_rule_condition,
    )

    payload = _require_mapping(path, value)
    if "type" in payload:
        raise EmaPullbackInstanceValidationError(LEGACY_PHASE_CONDITION_TYPE_ERROR)
    _reject_unknown_fields(path, payload, {"component_id", "params"})
    try:
        return parse_phase_rule_condition(
            _require_non_empty_str(payload, "component_id"),
            _require_present(payload, "params"),
            path=f"{path}.params",
        )
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _require_activate_when_phase(value: str, *, path: str) -> str:
    if value not in TRADE_MANAGEMENT_PHASES:
        allowed = ", ".join(repr(item) for item in TRADE_MANAGEMENT_PHASES)
        raise EmaPullbackInstanceValidationError(
            f"{path} must be one of: {allowed}; got {value!r}"
        )
    return value


def _require_positive_finite_float(raw: Any, *, path: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(f"{path} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise EmaPullbackInstanceValidationError(f"{path} must be a finite number > 0")
    return value


def _parse_management_activate_when(value: Any, *, path: str) -> ManagementActivateWhenSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"phase_at_least"})
    phase_at_least = _require_activate_when_phase(
        _require_non_empty_str(payload, "phase_at_least"),
        path=f"{path}.phase_at_least",
    )
    return ManagementActivateWhenSpec(phase_at_least=phase_at_least)  # type: ignore[arg-type]


def _parse_management_atr_ref(value: Any, *, path: str) -> ManagementAtrRefSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"timeframe", "period"})
    try:
        return ManagementAtrRefSpec(
            timeframe=_require_non_empty_str(payload, "timeframe"),
            period=int(_require_present(payload, "period")),
        )
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_stop_management_rules(value: Any) -> tuple[StopManagementRuleSpec, ...]:
    path = "trade_management.exit_management.stop_management"
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise EmaPullbackInstanceValidationError(f"{path} must be a list")
    return tuple(
        _parse_stop_management_rule(item, path=f"{path}[{i}]")
        for i, item in enumerate(value)
    )


def _parse_stop_management_rule(value: Any, *, path: str) -> StopManagementRuleSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"rule_id", "component_id", "activate_when", "params"})
    if "trigger" in payload:
        raise EmaPullbackInstanceValidationError(
            f"{path} must not include trigger in v2 stop_management"
        )
    component_id = _require_non_empty_str(payload, "component_id")
    if component_id not in STOP_MANAGEMENT_COMPONENT_IDS:
        allowed = ", ".join(repr(item) for item in STOP_MANAGEMENT_COMPONENT_IDS)
        raise EmaPullbackInstanceValidationError(
            f"{path}.component_id must be one of: {allowed}; got {component_id!r}"
        )
    params_raw = _require_present(payload, "params")
    if component_id == "break_even_stop":
        params = _parse_break_even_stop_params(params_raw, path=f"{path}.params")
    else:
        params = _parse_lock_profit_stop_params(params_raw, path=f"{path}.params")
    try:
        return StopManagementRuleSpec(
            rule_id=_require_non_empty_str(payload, "rule_id"),
            component_id=component_id,  # type: ignore[arg-type]
            activate_when=_parse_management_activate_when(
                _require_present(payload, "activate_when"),
                path=f"{path}.activate_when",
            ),
            params=params,
        )
    except ValueError as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_break_even_stop_params(value: Any, *, path: str) -> BreakEvenStopParamsSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(
        path,
        payload,
        {"buffer_type", "buffer", "buffer_atr", "atr_period", "atr"},
    )
    atr = None
    if "atr" in payload and payload["atr"] is not None:
        atr = _parse_management_atr_ref(payload["atr"], path=f"{path}.atr")
    try:
        return BreakEvenStopParamsSpec(
            buffer_type=payload.get("buffer_type", "none"),  # type: ignore[arg-type]
            buffer=float(payload.get("buffer", 0.0)),
            buffer_atr=float(payload.get("buffer_atr", 0.0)),
            atr_period=int(payload.get("atr_period", 14)),
            atr=atr,
        )
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_lock_profit_stop_params(value: Any, *, path: str) -> LockProfitStopParamsSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"lock_atr", "atr_period", "atr"})
    if "lock_atr" not in payload:
        raise EmaPullbackInstanceValidationError(f"{path}.lock_atr is required")
    atr = None
    if "atr" in payload and payload["atr"] is not None:
        atr = _parse_management_atr_ref(payload["atr"], path=f"{path}.atr")
    lock_atr = _require_positive_finite_float(
        _require_present(payload, "lock_atr"),
        path=f"{path}.lock_atr",
    )
    try:
        return LockProfitStopParamsSpec(
            lock_atr=lock_atr,
            atr_period=int(payload.get("atr_period", 14)),
            atr=atr,
        )
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_take_management_rules(value: Any) -> tuple[TakeManagementRuleSpec, ...]:
    path = "trade_management.exit_management.take_management"
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise EmaPullbackInstanceValidationError(f"{path} must be a list")
    return tuple(
        _parse_take_management_rule(item, path=f"{path}[{i}]")
        for i, item in enumerate(value)
    )


def _parse_take_management_rule(value: Any, *, path: str) -> TakeManagementRuleSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"rule_id", "component_id", "activate_when", "params"})
    component_id = _require_non_empty_str(payload, "component_id")
    if component_id != "take_profile_switch":
        raise EmaPullbackInstanceValidationError(
            f"{path}.component_id must be 'take_profile_switch'; got {component_id!r}"
        )
    try:
        return TakeManagementRuleSpec(
            rule_id=_require_non_empty_str(payload, "rule_id"),
            component_id="take_profile_switch",
            activate_when=_parse_management_activate_when(
                _require_present(payload, "activate_when"),
                path=f"{path}.activate_when",
            ),
            params=_parse_take_profile_switch_params(
                _require_present(payload, "params"),
                path=f"{path}.params",
            ),
        )
    except ValueError as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_take_profile_switch_params(
    value: Any,
    *,
    path: str,
) -> TakeProfileSwitchParamsSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"action"})
    action = _require_non_empty_str(payload, "action")
    if action == "disable_fixed_tp":
        action = "disable_initial_tp"
    try:
        return TakeProfileSwitchParamsSpec(
            action=action,  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_runtime_exit_rules(value: Any) -> tuple[RuntimeExitRuleSpec, ...]:
    path = "trade_management.exit_management.runtime_exits"
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise EmaPullbackInstanceValidationError(f"{path} must be a list")
    return tuple(
        _parse_runtime_exit_rule(item, path=f"{path}[{i}]")
        for i, item in enumerate(value)
    )


def _parse_runtime_exit_rule(value: Any, *, path: str) -> RuntimeExitRuleSpec:
    payload = _require_mapping(path, value)
    if "trigger" in payload:
        raise EmaPullbackInstanceValidationError(
            f"{path} must not include trigger in v2 runtime_exits"
        )
    _reject_unknown_fields(
        path,
        payload,
        {"rule_id", "component_id", "role", "activate_when", "exit_kind", "params"},
    )
    component_id = _require_non_empty_str(payload, "component_id")
    if component_id not in RUNTIME_EXIT_COMPONENT_IDS:
        allowed = ", ".join(repr(item) for item in RUNTIME_EXIT_COMPONENT_IDS)
        raise EmaPullbackInstanceValidationError(
            f"{path}.component_id must be one of: {allowed}; got {component_id!r}"
        )
    role = payload.get("role", RUNTIME_EXIT_ROLE)
    if not isinstance(role, str) or not role.strip():
        raise EmaPullbackInstanceValidationError(f"{path}.role must be a non-empty string")
    if role != RUNTIME_EXIT_ROLE:
        raise EmaPullbackInstanceValidationError(
            f"{path}.role must be {RUNTIME_EXIT_ROLE!r}; got {role!r}"
        )
    exit_kind_raw = payload.get("exit_kind")
    if component_id == "phase_runtime_exit":
        exit_kind = "market_close" if exit_kind_raw is None else str(exit_kind_raw)
    elif exit_kind_raw is None:
        raise EmaPullbackInstanceValidationError(f"{path}.exit_kind is required")
    else:
        exit_kind = str(exit_kind_raw)
    if exit_kind not in RUNTIME_EXIT_KINDS:
        allowed = ", ".join(repr(item) for item in RUNTIME_EXIT_KINDS)
        raise EmaPullbackInstanceValidationError(
            f"{path}.exit_kind must be one of: {allowed}; got {exit_kind!r}"
        )
    params_payload = _require_present(payload, "params")
    if component_id == "phase_runtime_exit":
        params = _parse_phase_runtime_exit_params(params_payload, path=f"{path}.params")
    elif component_id == "rsi_signal_exit":
        params = _parse_rsi_runtime_exit_params(params_payload, path=f"{path}.params")
    else:
        params = _parse_ema_cross_runtime_exit_params(params_payload, path=f"{path}.params")
    try:
        return RuntimeExitRuleSpec(
            rule_id=_require_non_empty_str(payload, "rule_id"),
            component_id=component_id,
            role=RUNTIME_EXIT_ROLE,
            activate_when=_parse_management_activate_when(
                _require_present(payload, "activate_when"),
                path=f"{path}.activate_when",
            ),
            exit_kind=exit_kind,  # type: ignore[arg-type]
            params=params,
        )
    except ValueError as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_rsi_runtime_exit_params(value: Any, *, path: str) -> RsiRuntimeExitParamsSpec:
    from research.strategies.ema_pullback.spec import RsiFeatureSpec

    payload = _require_mapping(path, value)
    rsi_raw = payload.get("rsi")
    if rsi_raw is None:
        raise EmaPullbackInstanceValidationError(f"{path} requires nested rsi object")
    rsi_map = _parse_rsi_payload(_require_mapping(f"{path}.rsi", rsi_raw))
    try:
        return RsiRuntimeExitParamsSpec(
            rsi=RsiFeatureSpec(
                timeframe=str(rsi_map["timeframe"]),
                period=int(rsi_map["period"]),
            ),
            long_exit_above=payload.get("long_exit_above"),
            short_exit_below=payload.get("short_exit_below"),
            confirm_bars=int(payload.get("confirm_bars", 1)),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_ema_cross_runtime_exit_params(
    value: Any,
    *,
    path: str,
) -> EmaCrossRuntimeExitParamsSpec:
    payload = _require_mapping(path, value)
    try:
        return EmaCrossRuntimeExitParamsSpec(
            fast_ema=_parse_ema_block(payload, key="fast_ema", path=path),
            slow_ema=_parse_ema_block(payload, key="slow_ema", path=path),
            confirm_bars=int(payload.get("confirm_bars", 1)),
        )
    except (TypeError, ValueError) as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _parse_phase_runtime_exit_params(
    value: Any,
    *,
    path: str,
) -> PhaseRuntimeExitParamsSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"exit_price"})
    exit_price = _require_non_empty_str(payload, "exit_price")
    if exit_price not in PHASE_RUNTIME_EXIT_PRICES:
        allowed = ", ".join(repr(item) for item in PHASE_RUNTIME_EXIT_PRICES)
        raise EmaPullbackInstanceValidationError(
            f"{path}.exit_price must be one of: {allowed}; got {exit_price!r}"
        )
    return PhaseRuntimeExitParamsSpec(exit_price=exit_price)  # type: ignore[arg-type]


def _parse_context_consumption(
    value: Any,
    *,
    path: str,
    allowed_policy_ids: tuple[str, ...],
) -> ContextConsumptionSpec | None:
    if value is None:
        return None
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"context_ref", "policy"})
    policy_path = f"{path}.policy"
    policy_payload = _require_mapping(policy_path, _require_present(payload, "policy"))
    _reject_unknown_fields(policy_path, policy_payload, {"policy_id", "params"})
    policy_id = _require_non_empty_str(policy_payload, "policy_id")
    if policy_id not in allowed_policy_ids:
        allowed = ", ".join(repr(item) for item in allowed_policy_ids)
        raise EmaPullbackInstanceValidationError(
            f"{policy_path}.policy_id must be one of: {allowed}; got {policy_id!r}"
        )
    params_raw = policy_payload.get("params", {})
    if params_raw is None:
        params_map: dict[str, Any] = {}
    else:
        params_map = _require_mapping(f"{policy_path}.params", params_raw)
    if policy_id == HTF_REGIME_GATE_POLICY:
        try:
            validate_htf_regime_gate_params(params_map, path=policy_path)
        except ValueError as exc:
            raise EmaPullbackInstanceValidationError(str(exc)) from exc
    params = tuple(sorted(params_map.items(), key=lambda item: item[0]))
    return ContextConsumptionSpec(
        context_ref=_require_non_empty_str(payload, "context_ref"),
        policy=ContextConsumptionPolicySpec(policy_id=policy_id, params=params),
    )


def _validate_profile_exits_require_consumption(
    profiles: ExitPolicyProfilesSpec,
    context_consumption: ContextConsumptionSpec | None,
) -> None:
    has_profile_exits = any(
        len(group.exits) > 0
        for group in (profiles.aligned, profiles.countertrend, profiles.neutral)
    )
    if has_profile_exits and context_consumption is None:
        raise EmaPullbackInstanceValidationError(
            "trade_management.exit_policy.context_consumption is required when "
            "profile-scoped exits are non-empty"
        )


def _parse_exit_policy_group(value: Any, *, path: str) -> ExitPolicyGroupSpec:
    payload = _require_mapping(path, value)
    _reject_unknown_fields(path, payload, {"exits"})
    exits_payload = _require_present(payload, "exits")
    if not isinstance(exits_payload, list):
        raise EmaPullbackInstanceValidationError(f"{path}.exits must be a list")
    exits = tuple(
        _parse_exit(index, item, path=f"{path}.exits")
        for index, item in enumerate(exits_payload)
    )
    return ExitPolicyGroupSpec(exits=exits)


def _parse_trade_sides(value: Any) -> tuple[TradeSide, ...]:
    trade_sides_value = value
    if isinstance(trade_sides_value, Mapping):
        if "enabled" in trade_sides_value:
            _reject_unknown_fields("strategy.trade_sides", trade_sides_value, {"enabled"})
            trade_sides_value = _require_present(trade_sides_value, "enabled")
        else:
            _reject_unknown_fields("strategy.trade_sides", trade_sides_value, {"long", "short"})
            return _parse_trade_side_flags(trade_sides_value)
    if not isinstance(trade_sides_value, Sequence) or isinstance(trade_sides_value, (str, bytes)):
        raise EmaPullbackInstanceValidationError("strategy.trade_sides must be a list")
    return builders.trade_sides(tuple(trade_sides_value)).enabled


def _parse_trade_side_flags(payload: Mapping[str, Any]) -> tuple[TradeSide, ...]:
    enabled: list[TradeSide] = []
    for side in ("long", "short"):
        value = payload.get(side, False)
        if not isinstance(value, bool):
            raise EmaPullbackInstanceValidationError(f"strategy.trade_sides.{side} must be a boolean")
        if value:
            enabled.append(side)
    return builders.trade_sides(tuple(enabled)).enabled


def _parse_anchor_stack(value: Any) -> dict[str, Any]:
    payload = _require_mapping("anchor_stack", value)
    _reject_unknown_fields("anchor_stack", payload, {"source", "timeframe", "fast", "anchor", "slow"})
    return {
        "source": _optional_non_empty_str(payload, "source", default="close"),
        "timeframe": _optional_non_empty_str(payload, "timeframe", default="base"),
        "fast": _require_positive_int(payload, "fast"),
        "anchor": _require_positive_int(payload, "anchor"),
        "slow": _require_positive_int(payload, "slow"),
    }


def _parse_direction(value: Any) -> str:
    component_id = _parse_component_id("direction", value)
    _assert_known_component("direction", component_id)
    if component_id != EMA_ANCHOR_STACK_TREND_COMPONENT:
        raise EmaPullbackInstanceValidationError(f"unsupported direction component_id {component_id!r}")
    return builders.direction_ema_anchor_stack()


def _migrate_legacy_setup_to_setups(strategy: dict[str, Any]) -> None:
    has_setups = "setups" in strategy and strategy["setups"] is not None
    has_setup = "setup" in strategy and strategy["setup"] is not None
    if has_setups and has_setup:
        raise EmaPullbackInstanceValidationError(
            "strategy must not contain both 'setup' and 'setups'"
        )
    if has_setups:
        return
    if not has_setup:
        return
    legacy = strategy.pop("setup")
    migrated = _require_mapping("strategy.setup", legacy)
    if "instance_id" not in migrated:
        migrated = {**migrated, "instance_id": "setup"}
    strategy["setups"] = [migrated]


def _parse_setups(
    value: Any,
    *,
    anchor_stack: Mapping[str, Any],
) -> tuple[SetupRuleSpec, ...]:
    if not isinstance(value, list) or not value:
        raise EmaPullbackInstanceValidationError("setups must be a non-empty list")
    return tuple(
        _parse_setup_rule(index, item, anchor_stack=anchor_stack)
        for index, item in enumerate(value)
    )


def _parse_setup_rule(
    index: int,
    value: Any,
    *,
    anchor_stack: Mapping[str, Any],
) -> SetupRuleSpec:
    path = f"setups[{index}]"
    payload = _component_mapping(
        path,
        value,
        extra_fields={
            "instance_id",
            "lookback",
            "active_bars",
            "params",
            "fast_ema",
            "anchor_ema",
            "slow_ema",
            "max_bounces",
            "raw_touch_mode",
            "touch_lookback_bars",
            "trend_start_confirmation_bars",
            "trend_break_confirmation_bars",
            "atr_timeframe",
            "atr_period",
            "min_current_width_atr",
            "min_recent_width_atr",
            "width_lookback_bars",
            "context_consumption",
        },
    )
    instance_id = _require_non_empty_str(payload, "instance_id")
    component_id = _require_non_empty_str(payload, "component_id")
    _assert_known_component("setup", component_id)
    context_consumption = _parse_context_consumption(
        payload.get("context_consumption"),
        path=f"{path}.context_consumption",
        allowed_policy_ids=(HTF_REGIME_GATE_POLICY,),
    )
    if component_id == UNTOUCHED_ANCHOR_SETUP_COMPONENT:
        lookback = _optional_positive_int(payload, "lookback", default=50)
        active_bars = _optional_positive_int(payload, "active_bars", default=3)
        return SetupRuleSpec(
            instance_id=instance_id,
            component_id=component_id,
            params=builders.untouched_anchor_setup_spec(
                lookback=lookback,
                active_bars=active_bars,
            ),
            context_consumption=context_consumption,
        )
    if component_id == EMA_BOUNCE_COUNTER_SETUP_COMPONENT:
        params_raw = payload.get("params", {})
        params = _require_mapping(f"{path}.params", params_raw) if params_raw else {}
        merged = {**payload, **params}
        _validate_legacy_bounce_setup_emas_match_anchor_stack(
            merged,
            anchor_stack=anchor_stack,
            instance_id=instance_id,
            path=path,
        )
        raw_touch_mode = str(merged.get("raw_touch_mode", "range_cross"))
        try:
            setup_spec = builders.ema_bounce_counter_setup_spec(
                max_bounces=_optional_positive_int(merged, "max_bounces", default=3),
                raw_touch_mode=raw_touch_mode,
                touch_lookback_bars=_optional_positive_int(
                    merged, "touch_lookback_bars", default=10
                ),
                trend_start_confirmation_bars=_optional_positive_int(
                    merged, "trend_start_confirmation_bars", default=1
                ),
                trend_break_confirmation_bars=_optional_positive_int(
                    merged, "trend_break_confirmation_bars", default=1
                ),
            )
        except ValueError as exc:
            raise EmaPullbackInstanceValidationError(str(exc)) from exc
        return SetupRuleSpec(
            instance_id=instance_id,
            component_id=component_id,
            params=setup_spec,
            context_consumption=context_consumption,
        )
    if component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT:
        params_raw = payload.get("params", {})
        params = _require_mapping(f"{path}.params", params_raw) if params_raw else {}
        merged = {**payload, **params}
        atr_timeframe = str(merged.get("atr_timeframe", "base")).strip()
        try:
            setup_spec = builders.anchor_stack_width_setup_spec(
                atr_timeframe=atr_timeframe,
                atr_period=_optional_positive_int(merged, "atr_period", default=14),
                min_current_width_atr=float(
                    merged.get("min_current_width_atr", 2.0)
                ),
                min_recent_width_atr=float(merged.get("min_recent_width_atr", 4.0)),
                width_lookback_bars=_optional_positive_int(
                    merged, "width_lookback_bars", default=80
                ),
            )
        except ValueError as exc:
            raise EmaPullbackInstanceValidationError(str(exc)) from exc
        return SetupRuleSpec(
            instance_id=instance_id,
            component_id=component_id,
            params=setup_spec,
            context_consumption=context_consumption,
        )
    raise EmaPullbackInstanceValidationError(f"unsupported setup component_id {component_id!r}")


def _parse_trigger(value: Any) -> Any:
    if isinstance(value, str):
        if not value.strip():
            raise EmaPullbackInstanceValidationError("trigger component_id must be non-empty")
        component_id = value.strip()
        payload: Mapping[str, Any] | None = None
    else:
        payload = _require_mapping("trigger", value)
        component_id = _require_non_empty_str(payload, "component_id")
    _assert_known_component("trigger", component_id)
    if component_id == RECLAIM_ANCHOR_COMPONENT:
        if payload is not None:
            _reject_unknown_fields("trigger", payload, {"component_id", "lookback"})
            lookback = _optional_positive_int(payload, "lookback", default=1)
        else:
            lookback = 1
        return builders.trigger_reclaim_anchor(lookback=lookback)
    if component_id == STRONG_RECLAIM_ANCHOR_COMPONENT:
        if payload is not None:
            _reject_unknown_fields("trigger", payload, {"component_id", "lookback"})
            lookback = _optional_positive_int(payload, "lookback", default=1)
        else:
            lookback = 1
        return builders.trigger_strong_reclaim_anchor(lookback=lookback)
    if component_id == TOUCH_ANCHOR_COMPONENT:
        if payload is not None:
            _reject_unknown_fields("trigger", payload, {"component_id"})
        return builders.trigger_touch_anchor()
    raise EmaPullbackInstanceValidationError(f"unsupported trigger component_id {component_id!r}")


def _parse_blockers(value: Any) -> tuple[BlockerRuleSpec, ...]:
    if not isinstance(value, list) or not value:
        raise EmaPullbackInstanceValidationError("blockers must be a non-empty list")
    return tuple(_parse_blocker(index, item) for index, item in enumerate(value))


def _parse_blocker(index: int, value: Any) -> BlockerRuleSpec:
    payload = _require_mapping(f"blockers[{index}]", value)
    component_id = _require_non_empty_str(payload, "component_id")
    _assert_known_component("blockers", component_id)
    instance_id = _require_non_empty_str(payload, "instance_id")
    common = {"instance_id", "component_id"}
    if component_id == NO_BLOCKERS_COMPONENT:
        _reject_unknown_fields(f"blockers[{index}]", payload, common)
        return builders.blocker_rule(NO_BLOCKERS_COMPONENT, instance_id=instance_id)
    if component_id == COUNTER_CANDLE_BLOCKER_COMPONENT:
        allowed = common | {"context_consumption"}
        _reject_unknown_fields(f"blockers[{index}]", payload, allowed)
        context_consumption = _parse_context_consumption(
            payload.get("context_consumption"),
            path=f"blockers[{index}].context_consumption",
            allowed_policy_ids=(HTF_REGIME_GATE_POLICY,),
        )
        return builders.blocker_counter_candle(
            instance_id=instance_id,
            context_consumption=context_consumption,
        )
    if component_id == RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT:
        allowed = common | {
            "rsi",
            "timeframe",
            "period",
            "lookback",
            "long_block_above",
            "short_block_below",
            "context_consumption",
        }
        _reject_unknown_fields(f"blockers[{index}]", payload, allowed)
        rsi = _parse_rsi_payload(payload)
        context_consumption = _parse_context_consumption(
            payload.get("context_consumption"),
            path=f"blockers[{index}].context_consumption",
            allowed_policy_ids=(HTF_REGIME_GATE_POLICY,),
        )
        return builders.blocker_extreme_rsi(
            instance_id=instance_id,
            timeframe=rsi["timeframe"],
            period=rsi["period"],
            lookback=_optional_positive_int(payload, "lookback", default=20),
            long_block_above=_optional_number(payload, "long_block_above", default=80.0),
            short_block_below=_optional_number(payload, "short_block_below", default=20.0),
            context_consumption=context_consumption,
        )
    if component_id == TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT:
        allowed = common | {
            "timeframe",
            "adx_period",
            "min_adx_peak",
            "peak_lookback_bars",
            "max_bars_since_peak",
            "min_current_adx",
            "require_di_alignment_on_peak",
            "block_on_opposite_di_flip",
            "opposite_di_margin",
            "require_ema_stack_direction",  # legacy; ignored at runtime
            "context_consumption",
        }
        _reject_unknown_fields(f"blockers[{index}]", payload, allowed)
        context_consumption = _parse_context_consumption(
            payload.get("context_consumption"),
            path=f"blockers[{index}].context_consumption",
            allowed_policy_ids=(HTF_REGIME_GATE_POLICY,),
        )
        try:
            return builders.blocker_trend_strength_episode(
                instance_id=instance_id,
                timeframe=str(payload.get("timeframe", "base")),
                adx_period=_optional_positive_int(payload, "adx_period", default=14),
                min_adx_peak=float(payload.get("min_adx_peak", 25.0)),
                peak_lookback_bars=_optional_positive_int(
                    payload, "peak_lookback_bars", default=60
                ),
                max_bars_since_peak=_optional_positive_int(
                    payload, "max_bars_since_peak", default=40
                ),
                min_current_adx=float(payload.get("min_current_adx", 12.0)),
                require_di_alignment_on_peak=_optional_bool(
                    payload, "require_di_alignment_on_peak", default=True
                ),
                block_on_opposite_di_flip=_optional_bool(
                    payload, "block_on_opposite_di_flip", default=True
                ),
                opposite_di_margin=float(payload.get("opposite_di_margin", 5.0)),
                context_consumption=context_consumption,
            )
        except ValueError as exc:
            raise EmaPullbackInstanceValidationError(str(exc)) from exc
    raise EmaPullbackInstanceValidationError(f"unsupported blocker component_id {component_id!r}")


def _parse_risk(value: Any) -> str:
    component_id = _parse_component_id("risk", value)
    _assert_known_component("risk", component_id)
    if component_id != NO_RISK_FILTER_COMPONENT:
        raise EmaPullbackInstanceValidationError(f"unsupported risk component_id {component_id!r}")
    return builders.risk_no_filter()


def _parse_exit(index: int, value: Any, *, path: str = "exits") -> ExitRuleSpec:
    payload = _require_mapping(f"{path}[{index}]", value)
    component_id = _require_non_empty_str(payload, "component_id")
    _assert_known_component("exits", component_id)
    instance_id = _require_non_empty_str(payload, "instance_id")
    common = {"instance_id", "component_id"}
    if component_id == NO_SIGNAL_EXIT_COMPONENT:
        _reject_unknown_fields(f"{path}[{index}]", payload, common)
        return builders.exit_rule(NO_SIGNAL_EXIT_COMPONENT, instance_id=instance_id, exit_kind="signal")
    if component_id == RSI_SIGNAL_EXIT_COMPONENT:
        allowed = common | {"rsi", "timeframe", "period", "long_exit_above", "short_exit_below"}
        _reject_unknown_fields(f"{path}[{index}]", payload, allowed)
        rsi = _parse_rsi_payload(payload)
        return builders.exit_rsi(
            instance_id=instance_id,
            timeframe=rsi["timeframe"],
            period=rsi["period"],
            long_exit_above=_optional_number(payload, "long_exit_above", default=70.0),
            short_exit_below=_optional_number(payload, "short_exit_below", default=30.0),
        )
    if component_id in {ATR_STOP_LOSS_COMPONENT, ATR_TAKE_PROFIT_COMPONENT}:
        allowed = common | {"distance", "timeframe", "period", "multiplier"}
        _reject_unknown_fields(f"{path}[{index}]", payload, allowed)
        distance = _parse_distance_payload(payload)
        if component_id == ATR_STOP_LOSS_COMPONENT:
            return builders.exit_atr_stop_loss(
                instance_id=instance_id,
                timeframe=distance["timeframe"],
                atr_period=distance["period"],
                atr_multiplier=distance["multiplier"],
            )
        return builders.exit_atr_take_profit(
            instance_id=instance_id,
            timeframe=distance["timeframe"],
            atr_period=distance["period"],
            atr_multiplier=distance["multiplier"],
        )
    if component_id in {CONSTANT_USD_STOP_LOSS_COMPONENT, CONSTANT_USD_TAKE_PROFIT_COMPONENT}:
        allowed = common | {"usd_distance"}
        _reject_unknown_fields(f"{path}[{index}]", payload, allowed)
        usd_distance = _require_positive_number(payload, "usd_distance")
        if component_id == CONSTANT_USD_STOP_LOSS_COMPONENT:
            return builders.exit_constant_usd_stop_loss(instance_id=instance_id, usd_distance=usd_distance)
        return builders.exit_constant_usd_take_profit(instance_id=instance_id, usd_distance=usd_distance)
    if component_id == EMA_CLOSE_LOSS_EXIT_COMPONENT:
        allowed = common | {"ema", "confirm_bars"}
        _reject_unknown_fields(f"{path}[{index}]", payload, allowed)
        ema = _parse_ema_block(payload, key="ema", path=f"{path}[{index}]")
        confirm_bars = _optional_positive_int(payload, "confirm_bars", default=1)
        return builders.exit_ema_close_loss(
            instance_id=instance_id,
            ema=ema,
            confirm_bars=confirm_bars,
        )
    if component_id == EMA_CROSS_LOSS_EXIT_COMPONENT:
        allowed = common | {"fast_ema", "slow_ema", "confirm_bars"}
        _reject_unknown_fields(f"{path}[{index}]", payload, allowed)
        fast_ema = _parse_ema_block(payload, key="fast_ema", path=f"{path}[{index}]")
        slow_ema = _parse_ema_block(payload, key="slow_ema", path=f"{path}[{index}]")
        confirm_bars = _optional_positive_int(payload, "confirm_bars", default=1)
        return builders.exit_ema_cross_loss(
            instance_id=instance_id,
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            confirm_bars=confirm_bars,
        )
    raise EmaPullbackInstanceValidationError(f"unsupported exit component_id {component_id!r}")


def _anchor_stack_ema_spec(anchor_stack: Mapping[str, Any], *, leg: str) -> EmaSpec:
    period_key = {"fast": "fast", "anchor": "anchor", "slow": "slow"}[leg]
    return builders.ema(
        int(anchor_stack[period_key]),
        timeframe=str(anchor_stack["timeframe"]),
        source=str(anchor_stack["source"]),
    )


def _optional_legacy_bounce_setup_ema(
    merged: Mapping[str, Any],
    key: str,
    *,
    path: str,
) -> EmaSpec | None:
    if key not in merged:
        return None
    raw = merged[key]
    if isinstance(raw, bool):
        raise EmaPullbackInstanceValidationError(f"{path}.{key} must be an EMA period or object")
    if isinstance(raw, int):
        if raw <= 0:
            raise EmaPullbackInstanceValidationError(f"{path}.{key} must be > 0")
        return builders.ema(raw, timeframe="base", source="close")
    ema_payload = _require_mapping(f"{path}.{key}", raw)
    _reject_unknown_fields(f"{path}.{key}", ema_payload, {"timeframe", "period", "source"})
    source = _optional_non_empty_str(ema_payload, "source", default="close")
    if source != "close":
        raise EmaPullbackInstanceValidationError(f"{path}.{key}.source must be 'close'")
    return builders.ema(
        _require_positive_int(ema_payload, "period"),
        timeframe=_optional_non_empty_str(ema_payload, "timeframe", default="base"),
        source=source,
    )


def _validate_legacy_bounce_setup_emas_match_anchor_stack(
    merged: Mapping[str, Any],
    *,
    anchor_stack: Mapping[str, Any],
    instance_id: str,
    path: str,
) -> None:
    checks = (
        ("fast_ema", "fast"),
        ("anchor_ema", "anchor"),
        ("slow_ema", "slow"),
    )
    mismatches: list[str] = []
    for setup_key, leg in checks:
        legacy = _optional_legacy_bounce_setup_ema(merged, setup_key, path=path)
        if legacy is None:
            continue
        expected = _anchor_stack_ema_spec(anchor_stack, leg=leg)
        if legacy != expected:
            mismatches.append(
                f"{setup_key}={legacy.period}@{legacy.timeframe} "
                f"(expected strategy.anchor_stack {leg}={expected.period}@{expected.timeframe})"
            )
    if mismatches:
        raise EmaPullbackInstanceValidationError(
            f"{path} (instance_id={instance_id!r}) legacy setup EMA params do not match "
            f"strategy.anchor_stack: {'; '.join(mismatches)}"
        )


def _parse_ema_block(payload: Mapping[str, Any], *, key: str, path: str) -> EmaSpec:
    nested = payload.get(key)
    if nested is None:
        raise EmaPullbackInstanceValidationError(f"{path} requires nested {key!r} object")
    ema_payload = _require_mapping(f"{path}.{key}", nested)
    _reject_unknown_fields(f"{path}.{key}", ema_payload, {"timeframe", "period", "source"})
    source = _optional_non_empty_str(ema_payload, "source", default="close")
    if source != "close":
        raise EmaPullbackInstanceValidationError(f"{path}.{key}.source must be 'close'")
    return builders.ema(
        _require_positive_int(ema_payload, "period"),
        timeframe=_optional_non_empty_str(ema_payload, "timeframe", default="base"),
        source=source,
    )


def _parse_rsi_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    nested = payload.get("rsi")
    if nested is not None:
        rsi = _require_mapping("rsi", nested)
        _reject_unknown_fields("rsi", rsi, {"timeframe", "period"})
        return {
            "timeframe": _optional_non_empty_str(rsi, "timeframe", default="base"),
            "period": _optional_positive_int(rsi, "period", default=14),
        }
    return {
        "timeframe": _optional_non_empty_str(payload, "timeframe", default="base"),
        "period": _optional_positive_int(payload, "period", default=14),
    }


def _parse_distance_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    nested = payload.get("distance")
    if nested is not None:
        distance = _require_mapping("distance", nested)
        _reject_unknown_fields("distance", distance, {"timeframe", "period", "multiplier"})
        return {
            "timeframe": _optional_non_empty_str(distance, "timeframe", default="base"),
            "period": _require_positive_int(distance, "period"),
            "multiplier": _require_positive_number(distance, "multiplier"),
        }
    return {
        "timeframe": _optional_non_empty_str(payload, "timeframe", default="base"),
        "period": _require_positive_int(payload, "period"),
        "multiplier": _require_positive_number(payload, "multiplier"),
    }


def _parse_component_id(name: str, value: Any) -> str:
    if isinstance(value, str):
        if not value.strip():
            raise EmaPullbackInstanceValidationError(f"{name} component_id must be non-empty")
        return value.strip()
    payload = _component_mapping(name, value)
    return _require_non_empty_str(payload, "component_id")


def _component_mapping(
    name: str,
    value: Any,
    *,
    extra_fields: set[str] | None = None,
) -> Mapping[str, Any]:
    payload = _require_mapping(name, value)
    _reject_unknown_fields(name, payload, {"component_id"} | (extra_fields or set()))
    return payload


def _assert_known_component(role: str, component_id: str) -> None:
    try:
        resolve_component(role, component_id)
    except ValueError as exc:
        raise EmaPullbackInstanceValidationError(str(exc)) from exc


def _reject_unknown_fields(name: str, payload: Mapping[str, Any], allowed: set[str] | frozenset[str]) -> None:
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise EmaPullbackInstanceValidationError(f"{name} has unknown field(s): {', '.join(unknown)}")


def _require_mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EmaPullbackInstanceValidationError(f"{name} must be an object")
    return value


def _require_present(payload: Mapping[str, Any], key: str) -> Any:
    if key not in payload:
        raise EmaPullbackInstanceValidationError(f"{key} is required")
    return payload[key]


def _require_non_empty_str(payload: Mapping[str, Any], key: str) -> str:
    value = _require_present(payload, key)
    if not isinstance(value, str) or not value.strip():
        raise EmaPullbackInstanceValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_non_empty_str(payload: Mapping[str, Any], key: str, *, default: str) -> str:
    if key not in payload:
        return default
    return _require_non_empty_str(payload, key)


def _require_positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = _require_present(payload, key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EmaPullbackInstanceValidationError(f"{key} must be a positive integer")
    return value


def _optional_positive_int(payload: Mapping[str, Any], key: str, *, default: int) -> int:
    if key not in payload:
        return default
    return _require_positive_int(payload, key)


def _require_positive_number(payload: Mapping[str, Any], key: str) -> float:
    value = _require_present(payload, key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise EmaPullbackInstanceValidationError(f"{key} must be a positive number")
    return float(value)


def _optional_number(payload: Mapping[str, Any], key: str, *, default: float) -> float:
    if key not in payload:
        return default
    value = payload[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise EmaPullbackInstanceValidationError(f"{key} must be a number")
    return float(value)


def _optional_bool(payload: Mapping[str, Any], key: str, *, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise EmaPullbackInstanceValidationError(
            f"{key} must be a boolean (true/false), got string {value!r}"
        )
    raise EmaPullbackInstanceValidationError(f"{key} must be a boolean")

