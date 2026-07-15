"""Shared context policy evaluation for all context-consuming call sites."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.policies import (
    EXIT_PROFILE_BY_HTF_STATE_POLICY,
    HTF_REGIME_GATE_POLICY,
    _allowed_regimes_from_policy,
    apply_exit_profile_by_htf_state,
    resolve_htf_regime,
)
from research.strategies.ema_pullback.spec import ContextConsumptionSpec, TradeSide

RegimeCache = dict[tuple[str, TradeSide], pd.Series]


@dataclass
class SideAwareEvaluationContext:
    """Side and bundle for one evaluation pass."""

    context_bundle: ContextBundle
    index: pd.Index
    evaluated_side: TradeSide | None = None
    enabled_sides: tuple[TradeSide, ...] | None = None
    regime_cache: RegimeCache | None = None


@dataclass
class ContextConsumptionResult:
    """Unified output from shared context policy evaluation."""

    policy_id: str
    context_ref: str
    allowed_mask: pd.Series | None = None
    profile_long: pd.Series | None = None
    profile_short: pd.Series | None = None
    raw_state_series: pd.Series | None = None
    resolved_regime_series: pd.Series | None = None
    evaluated_side: TradeSide | None = None
    outcome: dict[str, Any] = field(default_factory=dict)


def _resolved_regime_series(
    raw_state: pd.Series,
    *,
    context_ref: str,
    side: TradeSide,
    eval_ctx: SideAwareEvaluationContext,
) -> pd.Series:
    cache_key = (context_ref, side)
    if eval_ctx.regime_cache is not None and cache_key in eval_ctx.regime_cache:
        return eval_ctx.regime_cache[cache_key]
    resolved = raw_state.map(lambda state: resolve_htf_regime(state, side)).astype("object")
    if eval_ctx.regime_cache is not None:
        eval_ctx.regime_cache[cache_key] = resolved
    return resolved


def evaluate_context_consumption(
    consumption: ContextConsumptionSpec,
    eval_ctx: SideAwareEvaluationContext,
) -> ContextConsumptionResult:
    """Single entry point for policy-level ContextBundle consumption."""

    policy_id = consumption.policy.policy_id
    context_output = eval_ctx.context_bundle.get(consumption.context_ref)
    index = eval_ctx.index
    raw_state = context_output.state_series().reindex(index).fillna("neutral")

    if policy_id == HTF_REGIME_GATE_POLICY:
        side = eval_ctx.evaluated_side
        if side is None:
            raise ValueError("htf_regime_gate requires evaluated_side in SideAwareEvaluationContext")
        resolved = _resolved_regime_series(
            raw_state,
            context_ref=consumption.context_ref,
            side=side,
            eval_ctx=eval_ctx,
        )
        allowed_regimes = _allowed_regimes_from_policy(consumption.policy)
        allowed = resolved.isin(list(allowed_regimes)).astype(bool)
        return ContextConsumptionResult(
            policy_id=policy_id,
            context_ref=consumption.context_ref,
            allowed_mask=allowed,
            raw_state_series=raw_state,
            resolved_regime_series=resolved,
            evaluated_side=side,
            outcome={
                "evaluated_side": side,
                "allowed_regimes": sorted(allowed_regimes),
                "raw_state": raw_state.astype(str).tolist(),
                "resolved_regime": resolved.astype(str).tolist(),
            },
        )

    if policy_id == EXIT_PROFILE_BY_HTF_STATE_POLICY:
        if eval_ctx.enabled_sides is None:
            raise ValueError(
                "exit_profile_by_htf_state requires enabled_sides from evaluation scope"
            )
        profile_long, profile_short = apply_exit_profile_by_htf_state(
            raw_state,
            policy=consumption.policy,
            index=index,
            sides=eval_ctx.enabled_sides,
        )
        return ContextConsumptionResult(
            policy_id=policy_id,
            context_ref=consumption.context_ref,
            profile_long=profile_long,
            profile_short=profile_short,
            raw_state_series=raw_state,
            outcome={
                "profile_long": profile_long.astype(str).tolist(),
                "profile_short": profile_short.astype(str).tolist(),
            },
        )

    raise ValueError(f"unsupported context_consumption.policy_id: {policy_id!r}")
