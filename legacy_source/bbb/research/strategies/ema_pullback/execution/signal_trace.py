"""Per-bar entry pipeline trace for Workbench signal explanation (phase 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import pandas as pd

from research.strategies.ema_pullback.components.blockers import (
    counter_candle_blocker_trace,
    no_blockers_trace,
    rsi_lookback_extreme_blocker_trace,
    trend_strength_episode_blocker_trace,
)
from research.strategies.ema_pullback.components.direction import ema_anchor_stack_trend_trace
from research.strategies.ema_pullback.components.registry import (
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
    COUNTER_CANDLE_BLOCKER_COMPONENT,
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    NO_BLOCKERS_COMPONENT,
    RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
    TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT,
    RSI_SIGNAL_EXIT_COMPONENT,
    TOUCH_ANCHOR_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
)
from research.strategies.ema_pullback.components.setup import (
    anchor_stack_width_setup_trace,
    ema_bounce_counter_setup_trace,
    untouched_anchor_setup_trace,
)
from research.strategies.ema_pullback.components.triggers import (
    reclaim_anchor_trace,
    strong_reclaim_anchor_trace,
    touch_anchor_trace,
)
from research.strategies.ema_pullback.components.exits import rsi_signal_exit_trace
from research.strategies.ema_pullback.components.risk import no_risk_filter
from research.strategies.ema_pullback.context.consumption_trace import build_context_consumption_trace
from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.pipeline import build_context_bundle_for_spec
from research.strategies.ema_pullback.context.evaluation import (
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.execution.exits import build_exit_outputs_from_spec
from research.strategies.ema_pullback.execution.signals import (
    build_signals_from_spec,
    compose_blocker_signals,
    compose_final_signals,
)
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.setup_runtime import (
    compose_setup_masks,
    run_setup_rule_masks,
    run_setup_trace,
)
from research.strategies.ema_pullback.spec import (
    AnchorStackWidthSetupSpec,
    BlockerRuleSpec,
    EmaBounceCounterSetupSpec,
    EmaPullbackStrategySpec,
    ExitRuleSpec,
    ReclaimTriggerSpec,
    SetupRuleSpec,
    StrongReclaimTriggerSpec,
    RsiFeatureSpec,
    TradeSide,
    UntouchedAnchorSetupSpec,
)


class UnsupportedTraceComponentError(ValueError):
    """Component id has no trace implementation yet."""


_BLOCKER_TRACE: dict[str, Callable[..., dict[str, pd.Series]]] = {
    NO_BLOCKERS_COMPONENT: no_blockers_trace,
    COUNTER_CANDLE_BLOCKER_COMPONENT: counter_candle_blocker_trace,
    RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT: rsi_lookback_extreme_blocker_trace,
    TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT: trend_strength_episode_blocker_trace,
}

_SETUP_TRACE: dict[str, Callable[..., dict[str, pd.Series]]] = {
    UNTOUCHED_ANCHOR_SETUP_COMPONENT: untouched_anchor_setup_trace,
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT: ema_bounce_counter_setup_trace,
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT: anchor_stack_width_setup_trace,
}

_TRIGGER_TRACE: dict[str, Callable[..., dict[str, pd.Series]]] = {
    TOUCH_ANCHOR_COMPONENT: touch_anchor_trace,
}


def _rsi_column(plan: FeaturePlan, rsi: RsiFeatureSpec | None) -> str | None:
    if rsi is None:
        return None
    return plan.rsi_columns[(rsi.timeframe, rsi.period)]


def _false_series(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index, dtype=bool)


def _bool_list(series: pd.Series) -> list[bool]:
    return series.fillna(False).astype(bool).tolist()


def _float_list(series: pd.Series) -> list[float | None]:
    out: list[float | None] = []
    for value in series:
        if pd.isna(value):
            out.append(None)
        else:
            out.append(float(value))
    return out


def _object_list(series: pd.Series) -> list[Any]:
    out: list[Any] = []
    for value in series:
        if pd.isna(value):
            out.append(None)
        elif hasattr(value, "item"):
            out.append(value.item())
        else:
            out.append(value)
    return out


def _series_to_values(series: pd.Series) -> list[bool] | list[float | None] | list[Any]:
    if series.dtype == bool or str(series.dtype) == "boolean":
        return _bool_list(series)
    if series.dtype == object or str(series.dtype).startswith("string"):
        return _object_list(series)
    return _float_list(series)


def _serialize_internals(internals: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for section, content in internals.items():
        if section in ("blockers", "setups"):
            serialized[section] = {
                instance_id: {key: _series_to_values(series) for key, series in fields.items()}
                for instance_id, fields in content.items()
            }
        else:
            serialized[section] = {
                key: _series_to_values(series) for key, series in content.items()
            }
    return serialized


def _index_to_times_sec(index: pd.Index) -> list[int]:
    if isinstance(index, pd.DatetimeIndex):
        return [int(ts.timestamp()) for ts in index]
    raise TypeError("signal trace requires DatetimeIndex on OHLCV frame")


@dataclass(frozen=True)
class SideSignalTrace:
    direction_ok: list[bool]
    blockers_ok: list[bool]
    setup_ok: list[bool]
    trigger_ok: list[bool]
    risk_ok: list[bool]
    signal_entry: list[bool]
    stop_ready: list[bool]
    portfolio_entry: list[bool]
    internals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentEventData:
    time: int
    event_type: str
    role: str
    side: str
    component_id: str
    instance_id: str
    label: str
    tooltip: str | None = None
    span_id: str | None = None
    feature_family: str | None = None
    source_timeframe: str | None = None
    base_timeframe: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalTraceBundleData:
    times: list[int]
    meta: dict[str, Any]
    htf_context: dict[str, Any]
    context_consumption_trace: list[dict[str, Any]]
    component_events: list[ComponentEventData]
    long: SideSignalTrace
    short: SideSignalTrace


def _build_side_trace(
    *,
    df: pd.DataFrame,
    side: TradeSide,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    fast_col: str,
    anchor_col: str,
    slow_col: str,
    stop_ready: pd.Series,
    context_bundle: ContextBundle | None = None,
) -> SideSignalTrace:
    if not spec.trade_sides.includes(side):
        n = len(df)
        false = [False] * n
        true = [True] * n
        return SideSignalTrace(
            direction_ok=false,
            blockers_ok=true,
            setup_ok=false,
            trigger_ok=false,
            risk_ok=true,
            signal_entry=false,
            stop_ready=_bool_list(stop_ready),
            portfolio_entry=false,
            internals={},
        )

    trigger_rule = spec.components.trigger
    trigger_id = trigger_rule.component_id
    for setup_rule in spec.setups:
        if setup_rule.component_id not in _SETUP_TRACE:
            raise UnsupportedTraceComponentError(
                f"setup trace not implemented: {setup_rule.component_id!r}"
            )
    if (
        not isinstance(trigger_rule, ReclaimTriggerSpec | StrongReclaimTriggerSpec)
        and trigger_id not in _TRIGGER_TRACE
    ):
        raise UnsupportedTraceComponentError(f"trigger trace not implemented: {trigger_id!r}")

    direction_trace = ema_anchor_stack_trend_trace(
        df, fast_col, anchor_col, slow_col, side=side
    )
    direction = direction_trace["direction_ok"]

    blocker_traces: dict[str, dict[str, pd.Series]] = {}
    blocker_signals: list[pd.Series] = []
    for rule in spec.components.blockers:
        trace_fn = _BLOCKER_TRACE.get(rule.component_id)
        if trace_fn is None:
            raise UnsupportedTraceComponentError(
                f"blocker trace not implemented: {rule.component_id!r}"
            )
        if rule.component_id == RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT:
            trace = trace_fn(
                df,
                side=side,
                rule=rule,
                rsi_col=_rsi_column(plan, rule.rsi),
            )
        elif rule.component_id == TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT:
            if rule.trend_strength is None:
                raise ValueError("trend_strength_episode_blocker requires trend_strength params")
            cols = plan.adx_dmi_columns_for(rule.trend_strength)
            trace = trace_fn(
                df,
                side=side,
                rule=rule,
                adx_col=cols["adx"],
                di_plus_col=cols["di_plus"],
                di_minus_col=cols["di_minus"],
            )
        else:
            trace = trace_fn(df, side=side)
        allowed = trace["allowed"]
        consumption = rule.context_consumption
        if consumption is not None and context_bundle is not None:
            result = evaluate_context_consumption(
                consumption,
                SideAwareEvaluationContext(
                    context_bundle=context_bundle,
                    index=df.index,
                    evaluated_side=side,
                ),
            )
            gate = result.allowed_mask
            if gate is None:
                raise ValueError(
                    "context consumption result missing allowed_mask for "
                    f"{consumption.policy.policy_id!r}"
                )
            allowed = allowed & gate.fillna(False).astype(bool)
            trace = {**trace, "allowed": allowed, "htf_gate": gate}
        blocker_traces[rule.instance_id] = trace
        blocker_signals.append(allowed)

    blockers = compose_blocker_signals(tuple(blocker_signals))

    setup_traces: dict[str, dict[str, pd.Series]] = {}
    for setup_rule in spec.setups:
        local_trace = run_setup_trace(
            df,
            setup_rule,
            plan,
            anchor_col=anchor_col,
            side=side,
        )
        masks = run_setup_rule_masks(
            df,
            setup_rule,
            plan,
            anchor_col=anchor_col,
            side=side,
            context_bundle=context_bundle,
        )
        setup_traces[setup_rule.instance_id] = {
            **local_trace,
            "local_setup_allowed": masks.local_setup_allowed,
            "context_gate_allowed": masks.context_gate_allowed,
            "final_setup_allowed": masks.final_setup_allowed,
        }
    setup = compose_setup_masks(
        df,
        spec.setups,
        plan,
        anchor_col=anchor_col,
        side=side,
        context_bundle=context_bundle,
    )

    if isinstance(trigger_rule, ReclaimTriggerSpec):
        trigger_trace = reclaim_anchor_trace(
            df, anchor_col, trigger_rule.lookback, side=side
        )
    elif isinstance(trigger_rule, StrongReclaimTriggerSpec):
        trigger_trace = strong_reclaim_anchor_trace(
            df, anchor_col, trigger_rule.lookback, side=side
        )
    else:
        trigger_trace = _TRIGGER_TRACE[trigger_id](df, anchor_col, side=side)
    trigger = trigger_trace["trigger"]

    risk = no_risk_filter(df, side=side)

    signal_entry = compose_final_signals(
        direction_allowed=direction,
        blockers_ok=blockers,
        setup_ok=setup,
        trigger_ok=trigger,
        risk_ok=risk,
    )
    portfolio_entry = signal_entry & stop_ready

    internals: dict[str, Any] = {
        "direction": direction_trace,
        "setups": setup_traces,
        "trigger": trigger_trace,
        "blockers": blocker_traces,
    }

    return SideSignalTrace(
        direction_ok=_bool_list(direction),
        blockers_ok=_bool_list(blockers),
        setup_ok=_bool_list(setup),
        trigger_ok=_bool_list(trigger),
        risk_ok=_bool_list(risk),
        signal_entry=_bool_list(signal_entry),
        stop_ready=_bool_list(stop_ready),
        portfolio_entry=_bool_list(portfolio_entry),
        internals=_serialize_internals(internals),
    )


def _resolve_feature_timeframe(raw: str, base_timeframe: str) -> str:
    token = raw.strip()
    if token == "base":
        return base_timeframe
    return token


def _rising_edge_indices(values: list[bool]) -> list[int]:
    out: list[int] = []
    for i, active in enumerate(values):
        if active and (i == 0 or not values[i - 1]):
            out.append(i)
    return out


def _contiguous_blocked_runs(blocked: list[bool]) -> list[tuple[int, int]]:
    """Inclusive (start, end) indices where blocked is True."""

    runs: list[tuple[int, int]] = []
    i = 0
    n = len(blocked)
    while i < n:
        if not blocked[i]:
            i += 1
            continue
        start = i
        while i < n and blocked[i]:
            i += 1
        runs.append((start, i - 1))
    return runs


def _contiguous_true_runs(values: list[bool]) -> list[tuple[int, int]]:
    """Inclusive (start, end) indices where values is True."""

    return _contiguous_blocked_runs(values)


def _span_id(instance_id: str, side: TradeSide, span_start_time: int) -> str:
    return f"{instance_id}:{side}:{span_start_time}"


def _span_id_for_source_index(
    source_idx: int,
    blocked_runs: list[tuple[int, int]],
    times: list[int],
    instance_id: str,
    side: TradeSide,
) -> str | None:
    for start, end in blocked_runs:
        if start <= source_idx <= end:
            return _span_id(instance_id, side, times[start])
    for start, _end in blocked_runs:
        if source_idx <= start:
            return _span_id(instance_id, side, times[start])
    return None


def _event_label(event_type: str, role: str, side: TradeSide) -> str:
    if event_type == "source":
        return "Src"
    if role == "setup" and event_type == "span_start":
        return "Setup▶"
    if role == "setup" and event_type == "span_end":
        return "Setup■"
    if role == "setup" and event_type == "point":
        return "Trend"
    if event_type == "span_start":
        return "Block▶"
    if event_type == "span_end":
        return "Block■"
    if role == "exit_signal":
        return "Exit↓" if side == "long" else "Exit↑"
    return event_type


def _event_tooltip(
    *,
    event_type: str,
    role: str,
    component_id: str,
    instance_id: str,
    source_timeframe: str | None,
    base_timeframe: str | None,
    metadata: dict[str, Any],
) -> str:
    rsi_value = metadata.get("rsi_value")
    condition = metadata.get("condition", "")
    rsi_text = "—" if rsi_value is None else f"{rsi_value:.2f}"
    tf_text = (
        f"{source_timeframe}→{base_timeframe}"
        if source_timeframe and base_timeframe
        else ""
    )
    parts = [event_type, role, component_id, instance_id]
    if rsi_value is not None or condition:
        parts.append(f"RSI {rsi_text} · {condition}")
    if tf_text:
        parts.append(tf_text)
    return " · ".join(part for part in parts if part)


def _raw_rsi_threshold_series(
    df: pd.DataFrame,
    *,
    side: TradeSide,
    rule: BlockerRuleSpec,
    rsi_col: str,
) -> pd.Series:
    rsi = df[rsi_col].astype(float)
    if side == "long":
        if rule.long_block_above is None:
            raise ValueError(
                "rsi_lookback_extreme_blocker requires long_block_above for long side"
            )
        raw = rsi > float(rule.long_block_above)
    elif side == "short":
        if rule.short_block_below is None:
            raise ValueError(
                "rsi_lookback_extreme_blocker requires short_block_below for short side"
            )
        raw = rsi < float(rule.short_block_below)
    else:
        raise ValueError("side must be 'long' or 'short'")
    return raw.fillna(False).astype(bool)


def _sides_for_spec(spec: EmaPullbackStrategySpec) -> tuple[TradeSide, ...]:
    sides: list[TradeSide] = []
    if spec.trade_sides.includes("long"):
        sides.append("long")
    if spec.trade_sides.includes("short"):
        sides.append("short")
    return tuple(sides)


def _collect_rsi_exit_rules(spec: EmaPullbackStrategySpec) -> list[tuple[str, ExitRuleSpec]]:
    policy = spec.trade_management.exit_policy
    groups: list[tuple[str, tuple[ExitRuleSpec, ...]]] = [
        ("always_on", policy.always_on.exits),
        ("aligned", policy.profiles.aligned.exits),
        ("countertrend", policy.profiles.countertrend.exits),
        ("neutral", policy.profiles.neutral.exits),
    ]
    out: list[tuple[str, ExitRuleSpec]] = []
    seen: set[str] = set()
    for profile, rules in groups:
        for rule in rules:
            if rule.component_id != RSI_SIGNAL_EXIT_COMPONENT:
                continue
            if rule.instance_id in seen:
                continue
            seen.add(rule.instance_id)
            out.append((profile, rule))
    return out


def _anchor_stack_period_meta(spec: EmaPullbackStrategySpec) -> dict[str, int]:
    stack = spec.anchor_stack
    return {
        "fast_ema": stack.fast.period,
        "anchor_ema": stack.anchor.period,
        "slow_ema": stack.slow.period,
    }


def _setup_params_meta_for_rule(
    rule: SetupRuleSpec,
    spec: EmaPullbackStrategySpec,
) -> dict[str, Any]:
    if isinstance(rule.params, EmaBounceCounterSetupSpec):
        return {
            "instance_id": rule.instance_id,
            "component_id": rule.component_id,
            **_anchor_stack_period_meta(spec),
            "max_bounces": rule.params.max_bounces,
            "raw_touch_mode": rule.params.raw_touch_mode,
            "touch_lookback_bars": rule.params.touch_lookback_bars,
            "trend_start_confirmation_bars": rule.params.trend_start_confirmation_bars,
            "trend_break_confirmation_bars": rule.params.trend_break_confirmation_bars,
        }
    if isinstance(rule.params, UntouchedAnchorSetupSpec):
        return {
            "instance_id": rule.instance_id,
            "component_id": rule.component_id,
            "lookback": rule.params.lookback,
            "active_bars": rule.params.active_bars,
        }
    if isinstance(rule.params, AnchorStackWidthSetupSpec):
        return {
            "instance_id": rule.instance_id,
            "component_id": rule.component_id,
            "atr_timeframe": rule.params.atr_timeframe,
            "atr_period": rule.params.atr_period,
            "min_current_width_atr": rule.params.min_current_width_atr,
            "min_recent_width_atr": rule.params.min_recent_width_atr,
            "width_lookback_bars": rule.params.width_lookback_bars,
        }
    return {"instance_id": rule.instance_id, "component_id": rule.component_id}


def _setup_params_meta(spec: EmaPullbackStrategySpec) -> list[dict[str, Any]]:
    return [_setup_params_meta_for_rule(rule, spec) for rule in spec.setups]


def _rsi_blocker_threshold(rule: BlockerRuleSpec, side: TradeSide) -> float | None:
    if side == "long":
        return float(rule.long_block_above) if rule.long_block_above is not None else None
    if side == "short":
        return float(rule.short_block_below) if rule.short_block_below is not None else None
    raise ValueError("side must be 'long' or 'short'")


def _trace_bool_at(trace: dict[str, pd.Series], key: str, idx: int) -> bool:
    value = trace[key].iloc[idx]
    if pd.isna(value):
        return False
    return bool(value)


def _trace_int_at(trace: dict[str, pd.Series], key: str, idx: int) -> int:
    value = trace[key].iloc[idx]
    if pd.isna(value):
        return 0
    return int(value)


def _ema_bounce_metadata(
    rule: SetupRuleSpec,
    trace: dict[str, pd.Series],
    idx: int,
    spec: EmaPullbackStrategySpec,
    *,
    event_name: str,
) -> dict[str, Any]:
    if not isinstance(rule.params, EmaBounceCounterSetupSpec):
        return {"event_name": event_name}
    periods = _anchor_stack_period_meta(spec)
    return {
        "event_name": event_name,
        "trend_active": _trace_bool_at(trace, "trend_active", idx),
        "trend_episode_id": _trace_int_at(trace, "trend_episode_id", idx),
        "armed": _trace_bool_at(trace, "armed", idx),
        "raw_touch": _trace_bool_at(trace, "raw_touch", idx),
        "pending_bounce": _trace_bool_at(trace, "pending_bounce", idx),
        "in_touch_lookback": _trace_bool_at(trace, "in_touch_lookback", idx),
        "setup_allowed": _trace_bool_at(trace, "setup_allowed", idx),
        "touch_lookback_bars": int(rule.params.touch_lookback_bars),
        "touch_lookback_left": _trace_int_at(trace, "touch_lookback_left", idx),
        "completed_bounce_count": _trace_int_at(trace, "completed_bounce_count", idx),
        "effective_bounce_number": _trace_int_at(trace, "effective_bounce_number", idx),
        "max_bounces": int(rule.params.max_bounces),
        "price_side_of_anchor": str(trace["price_side_of_anchor"].iloc[idx]),
        "fast_ema": periods["fast_ema"],
        "anchor_ema": periods["anchor_ema"],
        "slow_ema": periods["slow_ema"],
    }


def _append_ema_bounce_counter_events(
    events: list[ComponentEventData],
    *,
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    times: list[int],
    base_timeframe: str,
) -> None:
    source_timeframe = base_timeframe
    bounce_rules = [
        rule
        for rule in spec.setups
        if rule.component_id == EMA_BOUNCE_COUNTER_SETUP_COMPONENT
    ]
    if not bounce_rules:
        return
    for rule in bounce_rules:
        if not isinstance(rule.params, EmaBounceCounterSetupSpec):
            continue
        instance_id = rule.instance_id
        for side in _sides_for_spec(spec):
            trace = ema_bounce_counter_setup_trace(
                df,
                plan.setup_columns_for(instance_id)["fast"],
                plan.setup_columns_for(instance_id)["anchor"],
                plan.setup_columns_for(instance_id)["slow"],
                max_bounces=rule.params.max_bounces,
                raw_touch_mode=rule.params.raw_touch_mode,
                touch_lookback_bars=rule.params.touch_lookback_bars,
                trend_start_confirmation_bars=rule.params.trend_start_confirmation_bars,
                trend_break_confirmation_bars=rule.params.trend_break_confirmation_bars,
                side=side,
            )
            starts = trace["pending_bounce_start"].fillna(False).astype(bool).to_list()
            ends = trace["pending_bounce_end"].fillna(False).astype(bool).to_list()
            for start_idx, active in enumerate(starts):
                if not active:
                    continue
                end_idx = min(
                    start_idx + rule.params.touch_lookback_bars - 1,
                    len(times) - 1,
                )
                while end_idx < len(ends) and not ends[end_idx] and end_idx + 1 < len(ends):
                    end_idx += 1
                run_span_id = _span_id(instance_id, side, times[start_idx])
                source_metadata = _ema_bounce_metadata(
                    rule,
                    trace,
                    start_idx,
                    spec,
                    event_name="bounce_opportunity_start",
                )
                events.append(
                    ComponentEventData(
                        time=times[start_idx],
                        event_type="source",
                        role="setup",
                        side=side,
                        component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
                        instance_id=instance_id,
                        label=_event_label("source", "setup", side),
                        tooltip=_event_tooltip(
                            event_type="source",
                            role="setup",
                            component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
                            instance_id=instance_id,
                            source_timeframe=source_timeframe,
                            base_timeframe=base_timeframe,
                            metadata=source_metadata,
                        ),
                        span_id=run_span_id,
                        feature_family="ema",
                        source_timeframe=source_timeframe,
                        base_timeframe=base_timeframe,
                        metadata=source_metadata,
                    )
                )
                for event_type, idx, event_name in (
                    ("span_start", start_idx, "pending_bounce_start"),
                    ("span_end", end_idx, "pending_bounce_end"),
                ):
                    metadata = _ema_bounce_metadata(
                        rule, trace, idx, spec, event_name=event_name
                    )
                    events.append(
                        ComponentEventData(
                            time=times[idx],
                            event_type=event_type,
                            role="setup",
                            side=side,
                            component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
                            instance_id=instance_id,
                            label=_event_label(event_type, "setup", side),
                            tooltip=_event_tooltip(
                                event_type=event_type,
                                role="setup",
                                component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
                                instance_id=instance_id,
                                source_timeframe=source_timeframe,
                                base_timeframe=base_timeframe,
                                metadata=metadata,
                            ),
                            span_id=run_span_id,
                            feature_family="ema",
                            source_timeframe=source_timeframe,
                            base_timeframe=base_timeframe,
                            metadata=metadata,
                        )
                    )
            for event_name, key in (
                ("trend_start", "trend_start_event"),
                ("trend_break", "trend_break_event"),
            ):
                for idx, active in enumerate(trace[key].fillna(False).astype(bool).to_list()):
                    if not active:
                        continue
                    metadata = _ema_bounce_metadata(
                        rule, trace, idx, spec, event_name=event_name
                    )
                    events.append(
                        ComponentEventData(
                            time=times[idx],
                            event_type="point",
                            role="setup",
                            side=side,
                            component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
                            instance_id=instance_id,
                            label=_event_label("point", "setup", side),
                            tooltip=_event_tooltip(
                                event_type="point",
                                role="setup",
                                component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
                                instance_id=instance_id,
                                source_timeframe=source_timeframe,
                                base_timeframe=base_timeframe,
                                metadata=metadata,
                            ),
                            feature_family="ema",
                            source_timeframe=source_timeframe,
                            base_timeframe=base_timeframe,
                            metadata=metadata,
                        )
                    )


def _format_width_tooltip(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _width_trace_float(trace: dict[str, pd.Series], key: str, idx: int) -> float | None:
    value = trace[key].iloc[idx]
    if pd.isna(value):
        return None
    return float(value)


def _anchor_stack_width_span_start_tooltip(
    trace: dict[str, pd.Series],
    idx: int,
    rule: SetupRuleSpec,
) -> str:
    assert isinstance(rule.params, AnchorStackWidthSetupSpec)
    params = rule.params
    lines = [
        "Anchor stack width setup",
        f"current_width_atr: {_width_trace_float(trace, 'current_width_atr', idx)}",
        f"recent_max_width_atr: {_width_trace_float(trace, 'recent_max_width_atr', idx)}",
        f"min_current_width_atr: {params.min_current_width_atr}",
        f"min_recent_width_atr: {params.min_recent_width_atr}",
        f"width_lookback_bars: {params.width_lookback_bars}",
        f"fast_ema: {_width_trace_float(trace, 'fast_ema', idx)}",
        f"anchor_ema: {_width_trace_float(trace, 'anchor_ema', idx)}",
        f"slow_ema: {_width_trace_float(trace, 'slow_ema', idx)}",
        f"atr_value: {_width_trace_float(trace, 'atr_value', idx)}",
    ]
    return _format_width_tooltip(lines)


def _anchor_stack_width_span_end_tooltip(
    trace: dict[str, pd.Series],
    last_allowed_idx: int,
    end_idx: int,
) -> str:
    reason = str(trace["blocked_reason"].iloc[end_idx] or "")
    lines = [
        "Anchor stack width ended",
        f"last_current_width_atr: {_width_trace_float(trace, 'current_width_atr', last_allowed_idx)}",
        f"last_recent_max_width_atr: {_width_trace_float(trace, 'recent_max_width_atr', last_allowed_idx)}",
        f"blocked_reason: {reason}",
    ]
    return _format_width_tooltip(lines)


def _append_anchor_stack_width_setup_events(
    events: list[ComponentEventData],
    *,
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    times: list[int],
    base_timeframe: str,
) -> None:
    width_rules = [
        rule
        for rule in spec.setups
        if rule.component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT
    ]
    if not width_rules:
        return
    source_timeframe = base_timeframe
    for rule in width_rules:
        if not isinstance(rule.params, AnchorStackWidthSetupSpec):
            continue
        instance_id = rule.instance_id
        cols = plan.setup_columns_for(instance_id)
        for side in _sides_for_spec(spec):
            trace = anchor_stack_width_setup_trace(
                df,
                cols["fast"],
                cols["anchor"],
                cols["slow"],
                cols["atr"],
                min_current_width_atr=rule.params.min_current_width_atr,
                min_recent_width_atr=rule.params.min_recent_width_atr,
                width_lookback_bars=rule.params.width_lookback_bars,
                side=side,
            )
            allowed = trace["setup_allowed"].fillna(False).astype(bool).tolist()
            for start, end in _contiguous_true_runs(allowed):
                run_span_id = _span_id(instance_id, side, times[start])
                start_metadata = {
                    "event_name": "width_ok",
                    "current_width_atr": _width_trace_float(trace, "current_width_atr", start),
                    "recent_max_width_atr": _width_trace_float(
                        trace, "recent_max_width_atr", start
                    ),
                    "min_current_width_atr": rule.params.min_current_width_atr,
                    "min_recent_width_atr": rule.params.min_recent_width_atr,
                    "width_lookback_bars": rule.params.width_lookback_bars,
                }
                events.append(
                    ComponentEventData(
                        time=times[start],
                        event_type="span_start",
                        role="setup",
                        side=side,
                        component_id=ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
                        instance_id=instance_id,
                        label="Width ok",
                        tooltip=_anchor_stack_width_span_start_tooltip(trace, start, rule),
                        span_id=run_span_id,
                        feature_family="ema",
                        source_timeframe=source_timeframe,
                        base_timeframe=base_timeframe,
                        metadata=start_metadata,
                    )
                )
                if end + 1 >= len(times):
                    continue
                end_idx = end + 1
                end_metadata = {
                    "event_name": "width_end",
                    "last_current_width_atr": _width_trace_float(
                        trace, "current_width_atr", end
                    ),
                    "last_recent_max_width_atr": _width_trace_float(
                        trace, "recent_max_width_atr", end
                    ),
                    "blocked_reason": str(trace["blocked_reason"].iloc[end_idx] or ""),
                }
                events.append(
                    ComponentEventData(
                        time=times[end_idx],
                        event_type="span_end",
                        role="setup",
                        side=side,
                        component_id=ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
                        instance_id=instance_id,
                        label="Width end",
                        tooltip=_anchor_stack_width_span_end_tooltip(trace, end, end_idx),
                        span_id=run_span_id,
                        feature_family="ema",
                        source_timeframe=source_timeframe,
                        base_timeframe=base_timeframe,
                        metadata=end_metadata,
                    )
                )


def build_component_events(
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    times: list[int],
) -> list[ComponentEventData]:
    """Semantic event emitters for configured catalog components."""

    if len(times) != len(df):
        raise ValueError("component_events requires times aligned with df index")

    base_timeframe = spec.base_timeframe
    events: list[ComponentEventData] = []

    _append_ema_bounce_counter_events(
        events,
        df=df,
        spec=spec,
        plan=plan,
        times=times,
        base_timeframe=base_timeframe,
    )
    _append_anchor_stack_width_setup_events(
        events,
        df=df,
        spec=spec,
        plan=plan,
        times=times,
        base_timeframe=base_timeframe,
    )

    for rule in spec.components.blockers:
        if rule.component_id != RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT:
            continue
        if rule.rsi is None:
            continue
        rsi_col = _rsi_column(plan, rule.rsi)
        if rsi_col is None:
            continue
        source_timeframe = _resolve_feature_timeframe(rule.rsi.timeframe, base_timeframe)
        for side in _sides_for_spec(spec):
            threshold = _rsi_blocker_threshold(rule, side)
            trace = rsi_lookback_extreme_blocker_trace(
                df,
                side=side,
                rule=rule,
                rsi_col=rsi_col,
            )
            allowed = trace["allowed"].fillna(True).astype(bool)
            rsi_series = trace["rsi"]
            raw = _raw_rsi_threshold_series(df, side=side, rule=rule, rsi_col=rsi_col)
            blocked = (~allowed).to_list()
            blocked_runs = _contiguous_blocked_runs(blocked)

            for source_idx in _rising_edge_indices(raw.to_list()):
                rsi_value = rsi_series.iloc[source_idx]
                rsi_float = None if pd.isna(rsi_value) else float(rsi_value)
                metadata = {
                    "rsi_value": rsi_float,
                    "condition": "threshold_cross",
                    "threshold": threshold,
                    "lookback": int(rule.lookback),
                    "period": int(rule.rsi.period),
                }
                span_id = _span_id_for_source_index(
                    source_idx,
                    blocked_runs,
                    times,
                    rule.instance_id,
                    side,
                )
                events.append(
                    ComponentEventData(
                        time=times[source_idx],
                        event_type="source",
                        role="entry_block",
                        side=side,
                        component_id=rule.component_id,
                        instance_id=rule.instance_id,
                        label=_event_label("source", "entry_block", side),
                        tooltip=_event_tooltip(
                            event_type="source",
                            role="entry_block",
                            component_id=rule.component_id,
                            instance_id=rule.instance_id,
                            source_timeframe=source_timeframe,
                            base_timeframe=base_timeframe,
                            metadata=metadata,
                        ),
                        span_id=span_id,
                        feature_family="rsi",
                        source_timeframe=source_timeframe,
                        base_timeframe=base_timeframe,
                        metadata=metadata,
                    )
                )

            for start, end in blocked_runs:
                span_start_time = times[start]
                run_span_id = _span_id(rule.instance_id, side, span_start_time)
                start_rsi = rsi_series.iloc[start]
                end_rsi = rsi_series.iloc[end]
                start_metadata = {
                    "rsi_value": None if pd.isna(start_rsi) else float(start_rsi),
                    "condition": "block_start",
                    "threshold": threshold,
                    "lookback": int(rule.lookback),
                    "period": int(rule.rsi.period),
                }
                end_metadata = {
                    "rsi_value": None if pd.isna(end_rsi) else float(end_rsi),
                    "condition": "block_end",
                    "threshold": threshold,
                    "lookback": int(rule.lookback),
                    "period": int(rule.rsi.period),
                }
                for event_type, idx, metadata in (
                    ("span_start", start, start_metadata),
                    ("span_end", end, end_metadata),
                ):
                    events.append(
                        ComponentEventData(
                            time=times[idx],
                            event_type=event_type,
                            role="entry_block",
                            side=side,
                            component_id=rule.component_id,
                            instance_id=rule.instance_id,
                            label=_event_label(event_type, "entry_block", side),
                            tooltip=_event_tooltip(
                                event_type=event_type,
                                role="entry_block",
                                component_id=rule.component_id,
                                instance_id=rule.instance_id,
                                source_timeframe=source_timeframe,
                                base_timeframe=base_timeframe,
                                metadata=metadata,
                            ),
                            span_id=run_span_id,
                            feature_family="rsi",
                            source_timeframe=source_timeframe,
                            base_timeframe=base_timeframe,
                            metadata=metadata,
                        )
                    )

    for profile, rule in _collect_rsi_exit_rules(spec):
        if rule.rsi is None:
            continue
        rsi_col = _rsi_column(plan, rule.rsi)
        if rsi_col is None:
            continue
        source_timeframe = _resolve_feature_timeframe(rule.rsi.timeframe, base_timeframe)
        for side in _sides_for_spec(spec):
            trace = rsi_signal_exit_trace(
                df,
                side=side,
                rule=rule,
                rsi_col=rsi_col,
            )
            exit_fired = trace["exit_fired"].fillna(False).astype(bool)
            rsi_series = trace["rsi"]
            condition = str(trace["condition"].iloc[0]) if len(trace["condition"]) else "exit"
            threshold = float(trace["threshold"].iloc[0]) if len(trace["threshold"]) else None
            for i, active in enumerate(exit_fired.to_list()):
                if not active:
                    continue
                rsi_value = rsi_series.iloc[i]
                rsi_float = None if pd.isna(rsi_value) else float(rsi_value)
                metadata = {
                    "rsi_value": rsi_float,
                    "condition": condition,
                    "threshold": threshold,
                    "profile": profile,
                    "period": int(rule.rsi.period),
                }
                events.append(
                    ComponentEventData(
                        time=times[i],
                        event_type="point",
                        role="exit_signal",
                        side=side,
                        component_id=rule.component_id,
                        instance_id=rule.instance_id,
                        label=_event_label("point", "exit_signal", side),
                        tooltip=_event_tooltip(
                            event_type="point",
                            role="exit_signal",
                            component_id=rule.component_id,
                            instance_id=rule.instance_id,
                            source_timeframe=source_timeframe,
                            base_timeframe=base_timeframe,
                            metadata=metadata,
                        ),
                        feature_family="rsi",
                        source_timeframe=source_timeframe,
                        base_timeframe=base_timeframe,
                        metadata=metadata,
                    )
                )

    events.sort(
        key=lambda event: (
            event.time,
            event.event_type,
            event.role,
            event.side,
            event.instance_id,
        )
    )
    return events


def build_signal_trace_from_spec(
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    *,
    context_overlay_ref: str | None = None,
) -> SignalTraceBundleData:
    """Full-index entry pipeline trace aligned with backtest signal composition."""

    fast_col = plan.anchor_columns["fast"]
    anchor_col = plan.anchor_columns["anchor"]
    slow_col = plan.anchor_columns["slow"]

    context_bundle = build_context_bundle_for_spec(spec, df, plan)
    exit_outputs = build_exit_outputs_from_spec(
        df, spec, plan, context_bundle=context_bundle
    )

    long_trace = _build_side_trace(
        df=df,
        side="long",
        spec=spec,
        plan=plan,
        fast_col=fast_col,
        anchor_col=anchor_col,
        slow_col=slow_col,
        stop_ready=exit_outputs.stop_ready_long,
        context_bundle=context_bundle,
    )
    short_trace = _build_side_trace(
        df=df,
        side="short",
        spec=spec,
        plan=plan,
        fast_col=fast_col,
        anchor_col=anchor_col,
        slow_col=slow_col,
        stop_ready=exit_outputs.stop_ready_short,
        context_bundle=context_bundle,
    )
    trigger_rule = spec.components.trigger
    overlay_ref = context_overlay_ref
    if overlay_ref is not None and overlay_ref not in spec.contexts_by_ref():
        raise ValueError(
            f"context_overlay_ref {overlay_ref!r} is not defined in strategy.contexts"
        )
    if overlay_ref is not None and context_bundle is not None:
        context_output = context_bundle.get(overlay_ref)
        context_cols = plan.htf_context_columns_for(overlay_ref)
        provider = spec.contexts_by_ref()[overlay_ref]
        htf_payload = {
            "state": [
                str(v) if isinstance(v, str) else "neutral"
                for v in context_output.state_series().to_list()
            ],
            "fast": _float_list(df[context_cols["fast"]].astype(float)),
            "anchor": _float_list(df[context_cols["anchor"]].astype(float)),
            "slow": _float_list(df[context_cols["slow"]].astype(float)),
            "meta": {
                "context_ref": overlay_ref,
                "component_id": provider.component_id,
                "timeframe": provider.timeframe,
                "source": provider.source,
                "fast_period": provider.fast_period,
                "anchor_period": provider.anchor_period,
                "slow_period": provider.slow_period,
            },
        }
    else:
        htf_payload = {
            "state": [],
            "fast": [],
            "anchor": [],
            "slow": [],
            "meta": {},
        }

    consumption_trace = build_context_consumption_trace(
        spec,
        df,
        plan,
        context_bundle=context_bundle,
        exit_outputs=exit_outputs,
        context_overlay_ref=overlay_ref,
    )
    meta = {
        "variant": spec.variant,
        "component_ids": {
            "direction": spec.components.direction,
            "setups": [
                {"instance_id": rule.instance_id, "component_id": rule.component_id}
                for rule in spec.setups
            ],
            "trigger": spec.components.trigger.component_id,
            "risk": spec.components.risk,
        },
        "setup_params": _setup_params_meta(spec),
        "trigger_params": (
            {"lookback": trigger_rule.lookback}
            if isinstance(trigger_rule, ReclaimTriggerSpec | StrongReclaimTriggerSpec)
            else {}
        ),
        "blocker_instances": [
            {"instance_id": rule.instance_id, "component_id": rule.component_id}
            for rule in spec.components.blockers
        ],
    }

    return SignalTraceBundleData(
        times=_index_to_times_sec(df.index),
        meta=meta,
        htf_context=htf_payload,
        context_consumption_trace=consumption_trace,
        component_events=build_component_events(
            df,
            spec,
            plan,
            _index_to_times_sec(df.index),
        ),
        long=long_trace,
        short=short_trace,
    )


def _slice_indexed_list(
    values: list[Any],
    indices: list[int],
    *,
    full_length: int,
) -> list[Any]:
    """Slice per-bar series only when aligned with ``trace.times`` (full_length)."""

    if not values or len(values) != full_length:
        return []
    return [values[i] for i in indices]


def slice_signal_trace(
    trace: SignalTraceBundleData,
    *,
    from_time_sec: int,
    to_time_sec: int,
    max_bars: int = 5000,
) -> SignalTraceBundleData:
    """Keep bars with ``from_time_sec <= time <= to_time_sec``, tail-capped at ``max_bars``."""

    indices = [i for i, t in enumerate(trace.times) if from_time_sec <= t <= to_time_sec]
    if len(indices) > max_bars:
        indices = indices[-max_bars:]
    full_length = len(trace.times)

    def _slice_side(side: SideSignalTrace) -> SideSignalTrace:
        def pick(values: list[bool]) -> list[bool]:
            return [values[i] for i in indices]

        def pick_internals(
            raw: dict[str, Any],
        ) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for section, content in raw.items():
                if section in ("blockers", "setups"):
                    out[section] = {
                        instance_id: {k: [v[j] for j in indices] for k, v in fields.items()}
                        for instance_id, fields in content.items()
                    }
                else:
                    out[section] = {k: [v[j] for j in indices] for k, v in content.items()}
            return out

        return SideSignalTrace(
            direction_ok=pick(side.direction_ok),
            blockers_ok=pick(side.blockers_ok),
            setup_ok=pick(side.setup_ok),
            trigger_ok=pick(side.trigger_ok),
            risk_ok=pick(side.risk_ok),
            signal_entry=pick(side.signal_entry),
            stop_ready=pick(side.stop_ready),
            portfolio_entry=pick(side.portfolio_entry),
            internals=pick_internals(side.internals),
        )

    def _slice_consumption_trace(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sliced_records: list[dict[str, Any]] = []
        for record in raw:
            applied = record.get("context_applied")
            if not isinstance(applied, list):
                sliced_records.append(record)
                continue
            next_record = dict(record)
            next_record["context_applied"] = _slice_indexed_list(
                applied,
                indices,
                full_length=full_length,
            )
            outcome = record.get("outcome")
            if isinstance(outcome, dict):
                next_outcome: dict[str, Any] = {}
                for key, values in outcome.items():
                    if isinstance(values, list):
                        next_outcome[key] = _slice_indexed_list(
                            values,
                            indices,
                            full_length=full_length,
                        )
                    else:
                        next_outcome[key] = values
                next_record["outcome"] = next_outcome
            sliced_records.append(next_record)
        return sliced_records

    htf = trace.htf_context
    times = [trace.times[i] for i in indices]
    allowed_times = set(times)
    return SignalTraceBundleData(
        times=times,
        meta=trace.meta,
        htf_context={
            "state": _slice_indexed_list(
                list(htf.get("state") or []),
                indices,
                full_length=full_length,
            ),
            "fast": _slice_indexed_list(
                list(htf.get("fast") or []),
                indices,
                full_length=full_length,
            ),
            "anchor": _slice_indexed_list(
                list(htf.get("anchor") or []),
                indices,
                full_length=full_length,
            ),
            "slow": _slice_indexed_list(
                list(htf.get("slow") or []),
                indices,
                full_length=full_length,
            ),
            "meta": htf.get("meta") or {},
        },
        context_consumption_trace=_slice_consumption_trace(trace.context_consumption_trace),
        component_events=[
            event
            for event in trace.component_events
            if event.time in allowed_times
        ],
        long=_slice_side(trace.long),
        short=_slice_side(trace.short),
    )
