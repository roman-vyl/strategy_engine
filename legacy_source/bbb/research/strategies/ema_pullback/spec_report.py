"""Deserialize ``EmaPullbackStrategySpec`` from report JSON (``asdict`` payload)."""

from __future__ import annotations

from typing import Any, Mapping

from research.strategies.ema_pullback.components.registry import (
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    RECLAIM_ANCHOR_COMPONENT,
    STRONG_RECLAIM_ANCHOR_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
)
from research.strategies.ema_pullback.spec import (
    AnchorStackSpec,
    AtrDistanceSpec,
    BlockerRuleSpec,
    ComponentStackSpec,
    EmaPullbackStrategySpec,
    AnchorStackWidthSetupSpec,
    EmaBounceCounterSetupSpec,
    EmaSpec,
    ExitPolicyGroupSpec,
    ExitPolicyProfilesSpec,
    ContextConsumptionPolicySpec,
    ContextConsumptionSpec,
    ContextProviderSpec,
    ExitPolicySpec,
    ExitRuleSpec,
    ReclaimTriggerSpec,
    SetupRuleSpec,
    StrongReclaimTriggerSpec,
    RsiFeatureSpec,
    TradeManagementSpec,
    TrendStrengthEpisodeBlockerParams,
    TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT,
    empty_exit_management,
    TradeSideSpec,
    TriggerSpec,
    UntouchedAnchorSetupSpec,
)


class StrategySpecReportParseError(ValueError):
    """Report ``strategy_spec`` dict cannot be parsed."""


def _require_mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StrategySpecReportParseError(f"{name} must be an object")
    return value


def _required_ema_spec(payload: Mapping[str, Any]) -> EmaSpec:
    return EmaSpec(
        source=str(payload["source"]),
        timeframe=str(payload["timeframe"]),
        period=int(payload["period"]),
    )


def _rsi_spec(payload: Mapping[str, Any] | None) -> RsiFeatureSpec | None:
    if payload is None:
        return None
    return RsiFeatureSpec(
        timeframe=str(payload.get("timeframe", "base")),
        period=int(payload.get("period", 14)),
    )


def _parse_policy_params(name: str, value: Any) -> tuple[tuple[str, Any], ...]:
    """Accept JSON object or legacy ``asdict`` list of ``[key, value]`` pairs."""
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple(sorted(value.items(), key=lambda item: item[0]))
    if isinstance(value, (list, tuple)):
        pairs: list[tuple[str, Any]] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                pairs.append((str(item[0]), item[1]))
            else:
                raise StrategySpecReportParseError(
                    f"{name} must be an object or list of [key, value] pairs"
                )
        return tuple(sorted(pairs, key=lambda pair: pair[0]))
    raise StrategySpecReportParseError(f"{name} must be an object")


def _parse_blocker_context_consumption(value: Any) -> ContextConsumptionSpec | None:
    if value is None:
        return None
    consumption = _require_mapping("blocker.context_consumption", value)
    policy = _require_mapping("blocker.context_consumption.policy", consumption.get("policy"))
    params = _parse_policy_params(
        "blocker.context_consumption.policy.params",
        policy.get("params", {}),
    )
    return ContextConsumptionSpec(
        context_ref=str(consumption["context_ref"]),
        policy=ContextConsumptionPolicySpec(
            policy_id=str(policy["policy_id"]),
            params=params,
        ),
    )


def _parse_setup_context_consumption(value: Any) -> ContextConsumptionSpec | None:
    if value is None:
        return None
    consumption = _require_mapping("setup.context_consumption", value)
    policy = _require_mapping("setup.context_consumption.policy", consumption.get("policy"))
    params = _parse_policy_params(
        "setup.context_consumption.policy.params",
        policy.get("params", {}),
    )
    return ContextConsumptionSpec(
        context_ref=str(consumption["context_ref"]),
        policy=ContextConsumptionPolicySpec(
            policy_id=str(policy["policy_id"]),
            params=params,
        ),
    )


def _trend_strength_params(payload: Any) -> TrendStrengthEpisodeBlockerParams | None:
    if payload is None:
        return None
    ts = _require_mapping("trend_strength", payload)
    return TrendStrengthEpisodeBlockerParams(
        timeframe=str(ts.get("timeframe", "base")),
        adx_period=int(ts.get("adx_period", 14)),
        min_adx_peak=float(ts.get("min_adx_peak", 25.0)),
        peak_lookback_bars=int(ts.get("peak_lookback_bars", 60)),
        max_bars_since_peak=int(ts.get("max_bars_since_peak", 40)),
        min_current_adx=float(ts.get("min_current_adx", 12.0)),
        require_di_alignment_on_peak=bool(
            ts.get("require_di_alignment_on_peak", True)
        ),
        block_on_opposite_di_flip=bool(ts.get("block_on_opposite_di_flip", True)),
        opposite_di_margin=float(ts.get("opposite_di_margin", 5.0)),
    )


def _blocker_rule(payload: Mapping[str, Any]) -> BlockerRuleSpec:
    component_id = str(payload["component_id"])
    trend_strength = (
        _trend_strength_params(payload.get("trend_strength"))
        if component_id == TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT
        else None
    )
    return BlockerRuleSpec(
        instance_id=str(payload["instance_id"]),
        component_id=component_id,
        rsi=_rsi_spec(payload.get("rsi")),
        lookback=int(payload.get("lookback", 20)),
        long_block_above=payload.get("long_block_above"),
        short_block_below=payload.get("short_block_below"),
        trend_strength=trend_strength,
        context_consumption=_parse_blocker_context_consumption(payload.get("context_consumption")),
    )


def _atr_distance(payload: Mapping[str, Any] | None) -> AtrDistanceSpec | None:
    if payload is None:
        return None
    return AtrDistanceSpec(
        timeframe=str(payload["timeframe"]),
        period=int(payload["period"]),
        multiplier=float(payload["multiplier"]),
    )


def _optional_ema_spec(name: str, payload: Any) -> EmaSpec | None:
    if payload is None:
        return None
    ema = _require_mapping(name, payload)
    return EmaSpec(
        source=str(ema.get("source", "close")),
        timeframe=str(ema["timeframe"]),
        period=int(ema["period"]),
    )


def _exit_rule(payload: Mapping[str, Any]) -> ExitRuleSpec:
    return ExitRuleSpec(
        instance_id=str(payload["instance_id"]),
        component_id=str(payload["component_id"]),
        exit_kind=str(payload.get("exit_kind", "signal")),
        rsi=_rsi_spec(payload.get("rsi")),
        ema=_optional_ema_spec("ema", payload.get("ema")),
        fast_ema=_optional_ema_spec("fast_ema", payload.get("fast_ema")),
        slow_ema=_optional_ema_spec("slow_ema", payload.get("slow_ema")),
        confirm_bars=int(payload.get("confirm_bars", 1)),
        long_exit_above=payload.get("long_exit_above"),
        short_exit_below=payload.get("short_exit_below"),
        distance=_atr_distance(payload.get("distance")),
        usd_distance=payload.get("usd_distance"),
    )


def _trigger_spec(
    payload: Mapping[str, Any],
) -> TriggerSpec | ReclaimTriggerSpec | StrongReclaimTriggerSpec:
    component_id = str(payload["component_id"])
    if component_id == RECLAIM_ANCHOR_COMPONENT:
        return ReclaimTriggerSpec(lookback=int(payload.get("lookback", 1)))
    if component_id == STRONG_RECLAIM_ANCHOR_COMPONENT:
        return StrongReclaimTriggerSpec(lookback=int(payload.get("lookback", 1)))
    return TriggerSpec(component_id=component_id)


def _setup_ema_spec(name: str, value: Any, *, default_period: int) -> EmaSpec:
    if isinstance(value, Mapping):
        return _optional_ema_spec(name, value) or EmaSpec(
            source="close", timeframe="base", period=default_period
        )
    if value is None:
        return EmaSpec(source="close", timeframe="base", period=default_period)
    return EmaSpec(source="close", timeframe="base", period=int(value))


def _parse_report_setups(raw: list[Any]) -> tuple[SetupRuleSpec, ...]:
    rules: list[SetupRuleSpec] = []
    for index, item in enumerate(raw):
        payload = _require_mapping(f"setups[{index}]", item)
        instance_id = str(payload.get("instance_id", "")).strip()
        if not instance_id:
            raise StrategySpecReportParseError(f"setups[{index}].instance_id must be non-empty")
        component_id = str(payload.get("component_id", "")).strip()
        if not component_id:
            raise StrategySpecReportParseError(f"setups[{index}].component_id must be non-empty")
        params = _setup_spec(component_id, payload)
        rules.append(
            SetupRuleSpec(
                instance_id=instance_id,
                component_id=component_id,
                params=params,
                context_consumption=_parse_setup_context_consumption(
                    payload.get("context_consumption")
                ),
            )
        )
    return tuple(rules)


def _setup_params_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Wire setups may store catalog params under nested ``params`` (asdict / API shape)."""

    nested = payload.get("params")
    if isinstance(nested, Mapping):
        return nested
    return payload


def _setup_spec(
    component_id: str, payload: Mapping[str, Any]
) -> UntouchedAnchorSetupSpec | EmaBounceCounterSetupSpec | AnchorStackWidthSetupSpec:
    source = _setup_params_payload(payload)
    if component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT:
        return AnchorStackWidthSetupSpec(
            atr_timeframe=str(source.get("atr_timeframe", "base")),
            atr_period=int(source.get("atr_period", 14)),
            min_current_width_atr=float(source.get("min_current_width_atr", 2.0)),
            min_recent_width_atr=float(source.get("min_recent_width_atr", 4.0)),
            width_lookback_bars=int(source.get("width_lookback_bars", 80)),
        )
    if component_id == EMA_BOUNCE_COUNTER_SETUP_COMPONENT:
        return EmaBounceCounterSetupSpec(
            max_bounces=int(source.get("max_bounces", 3)),
            raw_touch_mode=str(source.get("raw_touch_mode", "range_cross")),
            touch_lookback_bars=int(source.get("touch_lookback_bars", 10)),
            trend_start_confirmation_bars=int(source.get("trend_start_confirmation_bars", 1)),
            trend_break_confirmation_bars=int(source.get("trend_break_confirmation_bars", 1)),
        )
    if component_id == UNTOUCHED_ANCHOR_SETUP_COMPONENT:
        return UntouchedAnchorSetupSpec(
            lookback=int(source.get("lookback", 50)),
            active_bars=int(source.get("active_bars", 3)),
        )
    return UntouchedAnchorSetupSpec(
        lookback=int(source.get("lookback", 50)),
        active_bars=int(source.get("active_bars", 3)),
    )


def _exit_policy_group(payload: Mapping[str, Any], *, name: str) -> ExitPolicyGroupSpec:
    exits_raw = payload.get("exits")
    if not isinstance(exits_raw, (list, tuple)):
        raise StrategySpecReportParseError(f"{name}.exits must be a list")
    return ExitPolicyGroupSpec(exits=tuple(_exit_rule(_require_mapping(f"{name}.exits[]", e)) for e in exits_raw))


def strategy_spec_from_report_dict(payload: Mapping[str, Any]) -> EmaPullbackStrategySpec:
    """Rebuild spec from ``RunVariant.strategy_spec`` (``strategy_spec_to_dict`` shape)."""

    root = _require_mapping("strategy_spec", payload)
    stack_raw = _require_mapping("anchor_stack", root["anchor_stack"])
    components_raw = _require_mapping("components", root["components"])
    trade_sides_raw = _require_mapping("trade_sides", root["trade_sides"])
    setups_raw = root.get("setups")
    if not isinstance(setups_raw, (list, tuple)) or not setups_raw:
        raise StrategySpecReportParseError("setups must be a non-empty list")

    blockers_raw = components_raw.get("blockers")
    if not isinstance(blockers_raw, (list, tuple)):
        raise StrategySpecReportParseError("components.blockers must be a list")

    trigger_raw = components_raw.get("trigger")
    if not isinstance(trigger_raw, Mapping):
        raise StrategySpecReportParseError("components.trigger must be an object")

    enabled_raw = trade_sides_raw.get("enabled")
    if not isinstance(enabled_raw, (list, tuple)):
        raise StrategySpecReportParseError("trade_sides.enabled must be a list")

    tm_raw = _require_mapping("trade_management", root.get("trade_management"))
    ep_raw = _require_mapping(
        "trade_management.exit_policy",
        tm_raw.get("exit_policy"),
    )
    profiles_raw = _require_mapping("trade_management.exit_policy.profiles", ep_raw.get("profiles"))
    contexts = _parse_report_contexts(root.get("contexts"), ep_raw.get("context"))
    context_consumption = _parse_report_context_consumption(
        ep_raw.get("context_consumption"),
        legacy_context=ep_raw.get("context"),
        has_profile_exits=_report_has_profile_exits(profiles_raw),
    )
    from research.strategies.ema_pullback.instance_loader import _parse_exit_management

    exit_management = empty_exit_management()
    if "exit_management" in tm_raw:
        exit_management = _parse_exit_management(tm_raw["exit_management"])

    trade_management = TradeManagementSpec(
        exit_policy=ExitPolicySpec(
            always_on=_exit_policy_group(
                _require_mapping("trade_management.exit_policy.always_on", ep_raw.get("always_on")),
                name="trade_management.exit_policy.always_on",
            ),
            profiles=ExitPolicyProfilesSpec(
                aligned=_exit_policy_group(
                    _require_mapping("trade_management.exit_policy.profiles.aligned", profiles_raw.get("aligned")),
                    name="trade_management.exit_policy.profiles.aligned",
                ),
                countertrend=_exit_policy_group(
                    _require_mapping(
                        "trade_management.exit_policy.profiles.countertrend",
                        profiles_raw.get("countertrend"),
                    ),
                    name="trade_management.exit_policy.profiles.countertrend",
                ),
                neutral=_exit_policy_group(
                    _require_mapping("trade_management.exit_policy.profiles.neutral", profiles_raw.get("neutral")),
                    name="trade_management.exit_policy.profiles.neutral",
                ),
            ),
            context_consumption=context_consumption,
        ),
        exit_management=exit_management,
    )

    return EmaPullbackStrategySpec(
        variant=str(root["variant"]),
        symbol=str(root["symbol"]),
        base_timeframe=str(root["base_timeframe"]),
        anchor_stack=AnchorStackSpec(
            fast=_required_ema_spec(_require_mapping("fast", stack_raw["fast"])),
            anchor=_required_ema_spec(_require_mapping("anchor", stack_raw["anchor"])),
            slow=_required_ema_spec(_require_mapping("slow", stack_raw["slow"])),
        ),
        components=ComponentStackSpec(
            direction=str(components_raw["direction"]),
            blockers=tuple(_blocker_rule(b) for b in blockers_raw),
            trigger=_trigger_spec(trigger_raw),
            risk=str(components_raw["risk"]),
        ),
        trade_sides=TradeSideSpec(enabled=tuple(enabled_raw)),
        setups=_parse_report_setups(setups_raw),
        trade_management=trade_management,
        contexts=contexts,
    )


def _provider_from_report_mapping(
    context_ref: str,
    provider_raw: Any,
) -> tuple[str, ContextProviderSpec]:
    provider = _require_mapping(f"contexts.{context_ref}", provider_raw)
    return (
        str(context_ref),
        ContextProviderSpec(
            component_id=str(provider["component_id"]),
            timeframe=str(provider["timeframe"]),
            source=str(provider.get("source", "close")),
            fast_period=int(provider["fast_period"]),
            anchor_period=int(provider["anchor_period"]),
            slow_period=int(provider["slow_period"]),
        ),
    )


def _parse_report_contexts(
    contexts_raw: Any,
    legacy_context: Any,
) -> tuple[tuple[str, ContextProviderSpec], ...]:
    if isinstance(contexts_raw, Mapping) and contexts_raw:
        return tuple(
            _provider_from_report_mapping(context_ref, provider_raw)
            for context_ref, provider_raw in contexts_raw.items()
        )
    # Legacy reports: dataclasses.asdict serializes contexts as [(ref, provider_dict), ...].
    if isinstance(contexts_raw, (list, tuple)) and contexts_raw:
        providers: list[tuple[str, ContextProviderSpec]] = []
        for item in contexts_raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            context_ref, provider_raw = item[0], item[1]
            providers.append(_provider_from_report_mapping(str(context_ref), provider_raw))
        if providers:
            return tuple(providers)
    if isinstance(legacy_context, Mapping):
        return (
            (
                "htf",
                ContextProviderSpec(
                    component_id=str(legacy_context["component_id"]),
                    timeframe=str(legacy_context["timeframe"]),
                    source=str(legacy_context.get("source", "close")),
                    fast_period=int(legacy_context["fast_period"]),
                    anchor_period=int(legacy_context["anchor_period"]),
                    slow_period=int(legacy_context["slow_period"]),
                ),
            ),
        )
    return ()


def _parse_report_context_consumption(
    consumption_raw: Any,
    *,
    legacy_context: Any,
    has_profile_exits: bool,
) -> ContextConsumptionSpec | None:
    if isinstance(consumption_raw, Mapping):
        policy_raw = _require_mapping("context_consumption.policy", consumption_raw.get("policy"))
        params = _parse_policy_params(
            "context_consumption.policy.params",
            policy_raw.get("params", {}),
        )
        return ContextConsumptionSpec(
            context_ref=str(consumption_raw["context_ref"]),
            policy=ContextConsumptionPolicySpec(
                policy_id=str(policy_raw["policy_id"]),
                params=params,
            ),
        )
    if has_profile_exits and isinstance(legacy_context, Mapping):
        from research.strategies.ema_pullback.context.policies import EXIT_PROFILE_BY_HTF_STATE_POLICY

        return ContextConsumptionSpec(
            context_ref="htf",
            policy=ContextConsumptionPolicySpec(policy_id=EXIT_PROFILE_BY_HTF_STATE_POLICY, params=()),
        )
    return None


def _report_has_profile_exits(profiles_raw: Mapping[str, Any]) -> bool:
    for key in ("aligned", "countertrend", "neutral"):
        group = profiles_raw.get(key)
        if not isinstance(group, Mapping):
            continue
        exits = group.get("exits")
        if isinstance(exits, (list, tuple)) and len(exits) > 0:
            return True
    return False
