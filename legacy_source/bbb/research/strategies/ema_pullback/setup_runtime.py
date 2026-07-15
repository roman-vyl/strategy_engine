"""Dispatch setup stack instances to registry callables."""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from research.strategies.ema_pullback.components.registry import (
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
    resolve_component,
)
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.evaluation import (
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.spec import (
    AnchorStackWidthSetupSpec,
    EmaBounceCounterSetupSpec,
    SetupRuleSpec,
    TradeSide,
    UntouchedAnchorSetupSpec,
)


@dataclass(frozen=True)
class SetupRuleMasks:
    local_setup_allowed: pd.Series
    context_gate_allowed: pd.Series
    final_setup_allowed: pd.Series


def run_setup_mask(
    df: pd.DataFrame,
    rule: SetupRuleSpec,
    plan: FeaturePlan,
    *,
    anchor_col: str,
    side: TradeSide,
) -> pd.Series:
    fn = resolve_component("setup", rule.component_id).func
    if rule.component_id == EMA_BOUNCE_COUNTER_SETUP_COMPONENT:
        if not isinstance(rule.params, EmaBounceCounterSetupSpec):
            raise TypeError(
                f"setup {rule.instance_id!r} expects EmaBounceCounterSetupSpec params"
            )
        cols = plan.setup_columns_for(rule.instance_id)
        return fn(
            df,
            cols["fast"],
            cols["anchor"],
            cols["slow"],
            max_bounces=rule.params.max_bounces,
            raw_touch_mode=rule.params.raw_touch_mode,
            touch_lookback_bars=rule.params.touch_lookback_bars,
            trend_start_confirmation_bars=rule.params.trend_start_confirmation_bars,
            trend_break_confirmation_bars=rule.params.trend_break_confirmation_bars,
            side=side,
        )
    if rule.component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT:
        if not isinstance(rule.params, AnchorStackWidthSetupSpec):
            raise TypeError(
                f"setup {rule.instance_id!r} expects AnchorStackWidthSetupSpec params"
            )
        cols = plan.setup_columns_for(rule.instance_id)
        return fn(
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
    if rule.component_id == UNTOUCHED_ANCHOR_SETUP_COMPONENT:
        if not isinstance(rule.params, UntouchedAnchorSetupSpec):
            raise TypeError(
                f"setup {rule.instance_id!r} expects UntouchedAnchorSetupSpec params"
            )
        return fn(
            df,
            anchor_col,
            rule.params.lookback,
            rule.params.active_bars,
            side=side,
        )
    raise ValueError(f"unsupported setup component_id {rule.component_id!r}")


def run_setup_trace(
    df: pd.DataFrame,
    rule: SetupRuleSpec,
    plan: FeaturePlan,
    *,
    anchor_col: str,
    side: TradeSide,
) -> dict[str, pd.Series]:
    from research.strategies.ema_pullback.components.setup import (
        anchor_stack_width_setup_trace,
        ema_bounce_counter_setup_trace,
        untouched_anchor_setup_trace,
    )

    if rule.component_id == EMA_BOUNCE_COUNTER_SETUP_COMPONENT:
        if not isinstance(rule.params, EmaBounceCounterSetupSpec):
            raise TypeError(
                f"setup {rule.instance_id!r} expects EmaBounceCounterSetupSpec params"
            )
        cols = plan.setup_columns_for(rule.instance_id)
        return ema_bounce_counter_setup_trace(
            df,
            cols["fast"],
            cols["anchor"],
            cols["slow"],
            max_bounces=rule.params.max_bounces,
            raw_touch_mode=rule.params.raw_touch_mode,
            touch_lookback_bars=rule.params.touch_lookback_bars,
            trend_start_confirmation_bars=rule.params.trend_start_confirmation_bars,
            trend_break_confirmation_bars=rule.params.trend_break_confirmation_bars,
            side=side,
        )
    if rule.component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT:
        if not isinstance(rule.params, AnchorStackWidthSetupSpec):
            raise TypeError(
                f"setup {rule.instance_id!r} expects AnchorStackWidthSetupSpec params"
            )
        cols = plan.setup_columns_for(rule.instance_id)
        return anchor_stack_width_setup_trace(
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
    if rule.component_id == UNTOUCHED_ANCHOR_SETUP_COMPONENT:
        if not isinstance(rule.params, UntouchedAnchorSetupSpec):
            raise TypeError(
                f"setup {rule.instance_id!r} expects UntouchedAnchorSetupSpec params"
            )
        return untouched_anchor_setup_trace(
            df,
            anchor_col,
            rule.params.lookback,
            rule.params.active_bars,
            side=side,
        )
    raise ValueError(f"unsupported setup component_id {rule.component_id!r}")


def compose_setup_masks(
    df: pd.DataFrame,
    rules: tuple[SetupRuleSpec, ...],
    plan: FeaturePlan,
    *,
    anchor_col: str,
    side: TradeSide,
    context_bundle: ContextBundle | None = None,
) -> pd.Series:
    if not rules:
        raise ValueError("at least one setup rule is required")
    out = run_setup_rule_masks(
        df,
        rules[0],
        plan,
        anchor_col=anchor_col,
        side=side,
        context_bundle=context_bundle,
    ).final_setup_allowed
    for rule in rules[1:]:
        out = out & run_setup_rule_masks(
            df,
            rule,
            plan,
            anchor_col=anchor_col,
            side=side,
            context_bundle=context_bundle,
        ).final_setup_allowed
    return out.fillna(False).astype(bool)


def run_setup_rule_masks(
    df: pd.DataFrame,
    rule: SetupRuleSpec,
    plan: FeaturePlan,
    *,
    anchor_col: str,
    side: TradeSide,
    context_bundle: ContextBundle | None = None,
) -> SetupRuleMasks:
    local_mask = run_setup_mask(df, rule, plan, anchor_col=anchor_col, side=side).fillna(False).astype(bool)
    consumption = rule.context_consumption
    gate_mask = pd.Series(True, index=local_mask.index, dtype=bool)
    if consumption is None:
        return SetupRuleMasks(
            local_setup_allowed=local_mask,
            context_gate_allowed=gate_mask,
            final_setup_allowed=local_mask,
        )
    if context_bundle is None:
        raise ValueError(
            f"setups[{rule.instance_id!r}] requires context_bundle when context_consumption is configured"
        )
    result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=context_bundle,
            index=local_mask.index,
            evaluated_side=side,
        ),
    )
    gate = result.allowed_mask
    if gate is None:
        raise ValueError(
            "context consumption result missing allowed_mask for "
            f"{consumption.policy.policy_id!r}"
        )
    gate_mask = gate.fillna(False).astype(bool)
    return SetupRuleMasks(
        local_setup_allowed=local_mask,
        context_gate_allowed=gate_mask,
        final_setup_allowed=(local_mask & gate_mask).fillna(False).astype(bool),
    )
