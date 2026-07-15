"""Build per-consumer context consumption trace series for diagnostics."""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.evaluation import (
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.context.policies import HTF_REGIME_GATE_POLICY
from research.strategies.ema_pullback.execution.exits import PortfolioExitOutputs
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.setup_runtime import run_setup_mask
from research.strategies.ema_pullback.spec import (
    BlockerRuleSpec,
    EmaPullbackStrategySpec,
    SetupRuleSpec,
    TradeSide,
)


def _bool_list(series: pd.Series) -> list[bool]:
    return series.fillna(False).astype(bool).tolist()


def _blocker_trace_record(
    rule: BlockerRuleSpec,
    *,
    context_bundle: ContextBundle,
    index: pd.Index,
    evaluated_side: TradeSide | None = None,
    regime_cache: dict | None = None,
) -> dict[str, Any] | None:
    consumption = rule.context_consumption
    if consumption is None:
        return None
    result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=context_bundle,
            index=index,
            evaluated_side=evaluated_side,
            regime_cache=regime_cache,
        ),
    )
    gate = result.allowed_mask
    if gate is None:
        return None
    outcome: dict[str, Any] = dict(result.outcome)
    if consumption.policy.policy_id == HTF_REGIME_GATE_POLICY:
        outcome.setdefault("evaluated_side", evaluated_side)
    return {
        "role": "blockers",
        "component_id": rule.component_id,
        "instance_id": rule.instance_id,
        "context_ref": consumption.context_ref,
        "policy_id": consumption.policy.policy_id,
        "context_applied": _bool_list(gate),
        "outcome": outcome,
    }


def _setup_trace_record(
    rule: SetupRuleSpec,
    *,
    df: pd.DataFrame,
    plan: FeaturePlan,
    anchor_col: str,
    context_bundle: ContextBundle,
    evaluated_side: TradeSide,
    regime_cache: dict | None = None,
) -> dict[str, Any] | None:
    consumption = rule.context_consumption
    if consumption is None:
        return None
    local_mask = run_setup_mask(
        df,
        rule,
        plan,
        anchor_col=anchor_col,
        side=evaluated_side,
    ).fillna(False).astype(bool)
    result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=context_bundle,
            index=df.index,
            evaluated_side=evaluated_side,
            regime_cache=regime_cache,
        ),
    )
    gate = result.allowed_mask
    if gate is None:
        return None
    gate_mask = gate.fillna(False).astype(bool)
    final_mask = local_mask & gate_mask
    outcome: dict[str, Any] = dict(result.outcome)
    if consumption.policy.policy_id == HTF_REGIME_GATE_POLICY:
        outcome.setdefault("evaluated_side", evaluated_side)
    outcome["local_setup_allowed"] = _bool_list(local_mask)
    outcome["context_gate_allowed"] = _bool_list(gate_mask)
    outcome["final_setup_allowed"] = _bool_list(final_mask)
    return {
        "role": "setup",
        "component_id": rule.component_id,
        "instance_id": rule.instance_id,
        "setup_instance_id": rule.instance_id,
        "context_ref": consumption.context_ref,
        "policy_id": consumption.policy.policy_id,
        "context_applied": _bool_list(gate_mask),
        "outcome": outcome,
    }


def build_context_consumption_trace(
    spec: EmaPullbackStrategySpec,
    df: pd.DataFrame,
    plan: FeaturePlan,
    *,
    context_bundle: ContextBundle | None,
    exit_outputs: PortfolioExitOutputs,
    context_overlay_ref: str | None = None,
) -> list[dict[str, Any]]:
    """One record per consumer that applies context; per-bar ``context_applied`` lists."""

    if context_bundle is None or not spec.contexts:
        return []

    records: list[dict[str, Any]] = []
    index = df.index
    regime_cache: dict = {}

    exit_consumption = spec.trade_management.exit_policy.context_consumption
    if exit_consumption is not None:
        applied = pd.Series(True, index=index, dtype=bool)
        records.append(
            {
                "role": "exit_policy",
                "component_id": "exit_policy",
                "context_ref": exit_consumption.context_ref,
                "policy_id": exit_consumption.policy.policy_id,
                "context_applied": _bool_list(applied),
                "outcome": {
                    "profile_long": exit_outputs.profile_long.astype(str).tolist(),
                    "profile_short": exit_outputs.profile_short.astype(str).tolist(),
                },
            }
        )

    for rule in spec.components.blockers:
        consumption = rule.context_consumption
        if consumption is None:
            continue
        for side in spec.trade_sides.enabled:
            record = _blocker_trace_record(
                rule,
                context_bundle=context_bundle,
                index=index,
                evaluated_side=side,
                regime_cache=regime_cache,
            )
            if record is not None:
                records.append(record)
    anchor_col = plan.anchor_columns["anchor"]
    for rule in spec.setups:
        if rule.context_consumption is None:
            continue
        for side in spec.trade_sides.enabled:
            record = _setup_trace_record(
                rule,
                df=df,
                plan=plan,
                anchor_col=anchor_col,
                context_bundle=context_bundle,
                evaluated_side=side,
                regime_cache=regime_cache,
            )
            if record is not None:
                records.append(record)

    if context_overlay_ref and not context_bundle.has(context_overlay_ref):
        raise KeyError(f"unknown context_ref {context_overlay_ref!r}")

    return records


def _entry_gate_applied_at_idx(
    rule: BlockerRuleSpec,
    *,
    context_bundle: ContextBundle,
    index: pd.Index,
    entry_idx: int,
    trade_side: TradeSide,
) -> bool:
    consumption = rule.context_consumption
    if consumption is None:
        return False
    if entry_idx < 0 or entry_idx >= len(index):
        return False
    eval_side = trade_side
    result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=context_bundle,
            index=index,
            evaluated_side=eval_side,
        ),
    )
    gate = result.allowed_mask
    if gate is None:
        return True
    return bool(gate.iloc[entry_idx])


def consumption_attribution_for_trade(
    spec: EmaPullbackStrategySpec,
    *,
    entry_idx: int,
    direction: str,
    context_bundle: ContextBundle | None = None,
    index: pd.Index | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Wiring + entry-bar gate result for v5 trade_records.

  ``entry_context_consumption.applied`` is the context gate allow result on
  ``entry_idx`` when ``context_bundle`` and ``index`` are provided (same gate as trace).

  ``exit_context_consumption.applied`` means exit policy context consumption is configured
  (not a per-bar gate); causal exit profile selection stays in signal trace ``outcome``.
    """

    trade_side: TradeSide = "long" if direction == "long" else "short"
    consuming_blockers = [
        rule for rule in spec.components.blockers if rule.context_consumption is not None
    ]
    entry_consumption: dict[str, Any] | None = None
    if consuming_blockers:
        rule = consuming_blockers[-1]
        consumption = rule.context_consumption
        assert consumption is not None
        applied = True
        if context_bundle is not None and index is not None:
            applied = _entry_gate_applied_at_idx(
                rule,
                context_bundle=context_bundle,
                index=index,
                entry_idx=entry_idx,
                trade_side=trade_side,
            )
        entry_consumption = {
            "role": "blockers",
            "component_id": rule.component_id,
            "instance_id": rule.instance_id,
            "context_ref": consumption.context_ref,
            "policy_id": consumption.policy.policy_id,
            "applied": applied,
        }

    exit_consumption = spec.trade_management.exit_policy.context_consumption
    exit_attribution: dict[str, Any] | None = None
    if exit_consumption is not None:
        exit_attribution = {
            "role": "exit_policy",
            "component_id": "exit_policy",
            "context_ref": exit_consumption.context_ref,
            "policy_id": exit_consumption.policy.policy_id,
            "applied": True,
        }

    return entry_consumption, exit_attribution
