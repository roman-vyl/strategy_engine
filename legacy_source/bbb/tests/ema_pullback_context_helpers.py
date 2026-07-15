"""Shared helpers for strategy-level context tests."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.component_builders import (
    blocker_counter_candle,
    context_consumption,
    context_provider,
    exit_policy,
    strategy_contexts,
)
from research.strategies.ema_pullback.context.policies import (
    EXIT_PROFILE_BY_HTF_STATE_POLICY,
    HTF_REGIME_GATE_POLICY,
)
from research.strategies.ema_pullback.context.pipeline import build_context_bundle_for_spec
from research.strategies.ema_pullback.execution.exits import build_exit_outputs_from_spec
from research.strategies.ema_pullback.execution.exits import PortfolioExitOutputs
from research.strategies.ema_pullback.execution.signals import PortfolioSignals, build_signals_from_spec
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.spec import EmaPullbackStrategySpec, ExitRuleSpec


def context_bundle_for_spec(
    spec: EmaPullbackStrategySpec,
    df: pd.DataFrame,
    plan: FeaturePlan,
):
    return build_context_bundle_for_spec(spec, df, plan)


def build_signals_with_context_bundle(
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
) -> PortfolioSignals:
    return build_signals_from_spec(
        df,
        spec,
        plan,
        context_bundle=context_bundle_for_spec(spec, df, plan),
    )


def build_exit_outputs_with_context_bundle(
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
) -> PortfolioExitOutputs:
    bundle = context_bundle_for_spec(spec, df, plan)
    return build_exit_outputs_from_spec(df, spec, plan, context_bundle=bundle)


def htf_strategy_contexts(
    *,
    context_ref: str = "htf",
    timeframe: str = "4h",
    fast_period: int = 100,
    anchor_period: int = 200,
    slow_period: int = 1000,
):
    return strategy_contexts(
        (
            (
                context_ref,
                context_provider(
                    timeframe=timeframe,
                    fast_period=fast_period,
                    anchor_period=anchor_period,
                    slow_period=slow_period,
                ),
            ),
        )
    )


def exit_policy_htf_consumption(
    *,
    context_ref: str = "htf",
    always_on: tuple[ExitRuleSpec, ...] = (),
    aligned: tuple[ExitRuleSpec, ...] = (),
    countertrend: tuple[ExitRuleSpec, ...] = (),
    neutral: tuple[ExitRuleSpec, ...] = (),
):
    has_profile_exits = any(len(group) > 0 for group in (aligned, countertrend, neutral))
    return exit_policy(
        always_on=always_on,
        aligned=aligned,
        countertrend=countertrend,
        neutral=neutral,
        context_consumption_spec=(
            context_consumption(
                context_ref=context_ref,
                policy_id=EXIT_PROFILE_BY_HTF_STATE_POLICY,
            )
            if has_profile_exits
            else None
        ),
    )


def blocker_htf_regime_gate(
    *,
    context_ref: str = "htf",
    allowed_regimes: tuple[str, ...] = ("aligned",),
    instance_id: str = "counter_candle_blocker",
):
    return blocker_counter_candle(
        instance_id=instance_id,
        context_consumption=context_consumption(
            context_ref=context_ref,
            policy_id=HTF_REGIME_GATE_POLICY,
            params=(("allowed_regimes", list(allowed_regimes)),),
        ),
    )
