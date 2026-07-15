"""Composer: combine resolved pipeline components into final signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from research.strategies.ema_pullback.components.blockers import (
    build_trend_strength_blocker_counters,
    counter_candle_blocker,
    no_blockers,
    rsi_lookback_extreme_blocker,
    trend_strength_episode_blocker_trace,
)
from research.strategies.ema_pullback.components.registry import (
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
    COUNTER_CANDLE_BLOCKER_COMPONENT,
    NO_BLOCKERS_COMPONENT,
    RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
    TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT,
    resolve_component,
)
from research.strategies.ema_pullback.components.setup import (
    build_anchor_stack_width_setup_counters,
)
from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.pipeline import require_context_bundle
from research.strategies.ema_pullback.context.evaluation import (
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.spec import BlockerRuleSpec
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.setup_runtime import compose_setup_masks, run_setup_trace
from research.strategies.ema_pullback.spec import EmaPullbackStrategySpec
from research.strategies.ema_pullback.spec import ReclaimTriggerSpec, StrongReclaimTriggerSpec
from research.strategies.ema_pullback.spec import RsiFeatureSpec
from research.strategies.ema_pullback.spec import TradeSide


@dataclass(frozen=True)
class PortfolioSignals:
    entries: pd.Series
    short_entries: pd.Series
    output_counters: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _SideSignalOutputs:
    signal: pd.Series
    output_counters: tuple[dict[str, Any], ...]


def compose_final_signals(
    *,
    direction_allowed: pd.Series,
    blockers_ok: pd.Series,
    setup_ok: pd.Series,
    trigger_ok: pd.Series,
    risk_ok: pd.Series,
) -> pd.Series:
    """AND composition for one side entry signal."""

    final_entry = direction_allowed & blockers_ok & setup_ok & trigger_ok & risk_ok
    return final_entry.astype(bool)


def compose_blocker_signals(signals: tuple[pd.Series, ...]) -> pd.Series:
    """All blockers must allow the entry."""

    if not signals:
        raise ValueError("at least one blocker signal is required")
    out = signals[0].fillna(False).astype(bool)
    for signal in signals[1:]:
        out = out & signal.fillna(False).astype(bool)
    return out.astype(bool)


def _false_series(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index, dtype=bool)


def _apply_blocker_context_gate(
    signal: pd.Series,
    *,
    rule: BlockerRuleSpec,
    bundle: ContextBundle,
    side: TradeSide,
) -> pd.Series:
    consumption = rule.context_consumption
    if consumption is None:
        return signal
    result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=bundle,
            index=signal.index,
            evaluated_side=side,
        ),
    )
    gate = result.allowed_mask
    if gate is None:
        raise ValueError(
            "context consumption result missing allowed_mask for "
            f"{consumption.policy.policy_id!r}"
        )
    return signal & gate.fillna(False).astype(bool)


def _rsi_column(plan: FeaturePlan, rsi: RsiFeatureSpec | None) -> str | None:
    if rsi is None:
        return None
    return plan.rsi_columns[(rsi.timeframe, rsi.period)]


def _evaluate_blocker(
    df: pd.DataFrame,
    *,
    rule: BlockerRuleSpec,
    plan: FeaturePlan,
    side: TradeSide,
    fast_col: str,
    anchor_col: str,
    slow_col: str,
) -> tuple[pd.Series, dict[str, Any] | None]:
    if rule.component_id == TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT:
        if rule.trend_strength is None:
            raise ValueError("trend_strength_episode_blocker requires trend_strength params")
        cols = plan.adx_dmi_columns_for(rule.trend_strength)
        trace = trend_strength_episode_blocker_trace(
            df,
            side=side,
            rule=rule,
            adx_col=cols["adx"],
            di_plus_col=cols["di_plus"],
            di_minus_col=cols["di_minus"],
        )
        return trace["allowed"], {"trend_strength_trace": trace}
    if rule.component_id == RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT:
        signal = rsi_lookback_extreme_blocker(
            df, side=side, rule=rule, rsi_col=_rsi_column(plan, rule.rsi)
        )
        return signal, None
    if rule.component_id == COUNTER_CANDLE_BLOCKER_COMPONENT:
        return counter_candle_blocker(df, side=side), None
    if rule.component_id == NO_BLOCKERS_COMPONENT:
        return no_blockers(df, side=side), None
    fn = resolve_component("blockers", rule.component_id).func
    return fn(df, side=side, rule=rule, rsi_col=_rsi_column(plan, rule.rsi)), None


def _blocker_counter_entry(
    rule: BlockerRuleSpec,
    side: TradeSide,
    signal: pd.Series,
    extra_counters: dict[str, Any] | None,
) -> dict[str, Any]:
    allowed = signal.fillna(False).astype(bool)
    counters: dict[str, Any] = {
        "allowed_count": int(allowed.sum()),
        "blocked_count": int((~allowed).sum()),
    }
    if extra_counters is not None:
        trace = extra_counters.get("trend_strength_trace")
        if trace is not None:
            counters = build_trend_strength_blocker_counters(
                trace, final_allowed=allowed
            )
        else:
            counters.update(extra_counters)
    return {
        "role": "blockers",
        "component_id": rule.component_id,
        "instance_id": rule.instance_id,
        "side": side,
        "output_type": "allow_mask",
        "counters": counters,
    }


def _build_side_signals(
    *,
    df: pd.DataFrame,
    side: TradeSide,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    fast_col: str,
    anchor_col: str,
    slow_col: str,
    direction_fn: Callable[..., pd.Series],
    trigger_fn: Callable[..., pd.Series],
    risk_fn: Callable[..., pd.Series],
    context_bundle: ContextBundle | None,
) -> _SideSignalOutputs:
    if not spec.trade_sides.includes(side):
        return _SideSignalOutputs(signal=_false_series(df), output_counters=())

    direction = direction_fn(df, fast_col, anchor_col, slow_col, side=side)
    bundle = require_context_bundle(spec, context_bundle)
    blocker_signals_list: list[pd.Series] = []
    blocker_counters_list: list[dict[str, Any]] = []
    for rule in spec.components.blockers:
        signal, extra_counters = _evaluate_blocker(
            df,
            rule=rule,
            plan=plan,
            side=side,
            fast_col=fast_col,
            anchor_col=anchor_col,
            slow_col=slow_col,
        )
        if rule.context_consumption is not None:
            assert bundle is not None
            signal = _apply_blocker_context_gate(signal, rule=rule, bundle=bundle, side=side)
        blocker_signals_list.append(signal)
        blocker_counters_list.append(
            _blocker_counter_entry(rule, side, signal, extra_counters)
        )
    blocker_signals = tuple(blocker_signals_list)
    blocker_counters = tuple(blocker_counters_list)
    blockers = compose_blocker_signals(blocker_signals)
    setup = compose_setup_masks(
        df,
        spec.setups,
        plan,
        anchor_col=anchor_col,
        side=side,
        context_bundle=bundle,
    )
    setup_counter_entries: list[dict[str, Any]] = []
    for rule in spec.setups:
        if rule.component_id != ANCHOR_STACK_WIDTH_SETUP_COMPONENT:
            continue
        trace = run_setup_trace(
            df,
            rule,
            plan,
            anchor_col=anchor_col,
            side=side,
        )
        setup_counter_entries.append(
            {
                "role": "setup",
                "component_id": rule.component_id,
                "instance_id": rule.instance_id,
                "side": side,
                "output_type": "allow_mask",
                "counters": build_anchor_stack_width_setup_counters(trace),
            }
        )
    trigger_rule = spec.components.trigger
    if isinstance(trigger_rule, ReclaimTriggerSpec | StrongReclaimTriggerSpec):
        trigger = trigger_fn(df, anchor_col, trigger_rule.lookback, side=side)
    else:
        trigger = trigger_fn(df, anchor_col, side=side)
    risk = risk_fn(df, side=side)

    return _SideSignalOutputs(
        signal=compose_final_signals(
            direction_allowed=direction,
            blockers_ok=blockers,
            setup_ok=setup,
            trigger_ok=trigger,
            risk_ok=risk,
        ),
        output_counters=blocker_counters + tuple(setup_counter_entries),
    )


def build_signals_from_spec(
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    *,
    context_bundle: ContextBundle | None = None,
) -> PortfolioSignals:
    """Build entry signals via component registry using StrategySpec ids."""

    require_context_bundle(spec, context_bundle)
    direction_fn = resolve_component("direction", spec.components.direction).func
    trigger_fn = resolve_component("trigger", spec.components.trigger.component_id).func
    risk_fn = resolve_component("risk", spec.components.risk).func

    fast_col = plan.anchor_columns["fast"]
    anchor_col = plan.anchor_columns["anchor"]
    slow_col = plan.anchor_columns["slow"]

    long_outputs = _build_side_signals(
        df=df,
        side="long",
        spec=spec,
        plan=plan,
        fast_col=fast_col,
        anchor_col=anchor_col,
        slow_col=slow_col,
        direction_fn=direction_fn,
        trigger_fn=trigger_fn,
        risk_fn=risk_fn,
        context_bundle=context_bundle,
    )
    short_outputs = _build_side_signals(
        df=df,
        side="short",
        spec=spec,
        plan=plan,
        fast_col=fast_col,
        anchor_col=anchor_col,
        slow_col=slow_col,
        direction_fn=direction_fn,
        trigger_fn=trigger_fn,
        risk_fn=risk_fn,
        context_bundle=context_bundle,
    )

    return PortfolioSignals(
        entries=long_outputs.signal,
        short_entries=short_outputs.signal,
        output_counters=long_outputs.output_counters + short_outputs.output_counters,
    )

