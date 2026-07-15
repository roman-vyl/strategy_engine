from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from research.strategies.ema_pullback.components.exits import (
    ema_cross_loss_exit,
    rsi_signal_exit,
)
from research.strategies.ema_pullback.consumer_roles import ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT
from research.strategies.ema_pullback.execution.managed_components.activation import (
    phase_at_least_met,
)
from research.strategies.ema_pullback.execution.trade_runtime import ManagedExitContext
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.spec import (
    EmaCrossRuntimeExitParamsSpec,
    ExitRuleSpec,
    PhaseRuntimeExitParamsSpec,
    RsiRuntimeExitParamsSpec,
    RuntimeExitKind,
    RuntimeExitRuleSpec,
)


@dataclass(frozen=True)
class RuntimeExitTrigger:
    rule_id: str
    component_id: str
    exit_price: float
    exit_kind: RuntimeExitKind
    role: str = ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT


def _runtime_exit_rule_to_exit_rule(
    rule: RuntimeExitRuleSpec,
) -> ExitRuleSpec:
    if isinstance(rule.params, RsiRuntimeExitParamsSpec):
        params = rule.params
        return ExitRuleSpec(
            instance_id=rule.rule_id,
            component_id=rule.component_id,
            exit_kind="signal",
            rsi=params.rsi,
            long_exit_above=params.long_exit_above,
            short_exit_below=params.short_exit_below,
            confirm_bars=params.confirm_bars,
        )
    if isinstance(rule.params, EmaCrossRuntimeExitParamsSpec):
        params = rule.params
        return ExitRuleSpec(
            instance_id=rule.rule_id,
            component_id=rule.component_id,
            exit_kind="signal",
            fast_ema=params.fast_ema,
            slow_ema=params.slow_ema,
            confirm_bars=params.confirm_bars,
        )
    raise ValueError(f"unsupported runtime exit component {rule.component_id!r}")


def compile_runtime_exit_signal_series(
    rule: RuntimeExitRuleSpec,
    *,
    df: pd.DataFrame,
    plan: FeaturePlan,
    side: Literal["long", "short"],
) -> pd.Series | None:
    if rule.component_id == "phase_runtime_exit":
        return None
    exit_rule = _runtime_exit_rule_to_exit_rule(rule)
    if rule.component_id == "rsi_signal_exit":
        assert isinstance(rule.params, RsiRuntimeExitParamsSpec)
        rsi_col = plan.rsi_columns.get(
            (rule.params.rsi.timeframe, rule.params.rsi.period)
        )
        if rsi_col is None:
            return None
        return rsi_signal_exit(df, side=side, rule=exit_rule, rsi_col=rsi_col)
    if rule.component_id == "ema_cross_loss_exit":
        assert isinstance(rule.params, EmaCrossRuntimeExitParamsSpec)
        fast_col = plan.ema_columns.get(
            (rule.params.fast_ema.timeframe, rule.params.fast_ema.period)
        )
        slow_col = plan.ema_columns.get(
            (rule.params.slow_ema.timeframe, rule.params.slow_ema.period)
        )
        if fast_col is None or slow_col is None:
            return None
        return ema_cross_loss_exit(
            df,
            side=side,
            rule=exit_rule,
            fast_col=fast_col,
            slow_col=slow_col,
        )
    return None


def evaluate_runtime_exits(
    rules: tuple[RuntimeExitRuleSpec, ...],
    *,
    context: ManagedExitContext,
    signal_series_by_rule_id: dict[str, pd.Series] | None = None,
) -> list[RuntimeExitTrigger]:
    triggers: list[RuntimeExitTrigger] = []
    signals = signal_series_by_rule_id or {}
    for rule in rules:
        if not phase_at_least_met(context.phase, rule.activate_when.phase_at_least):
            continue
        if rule.component_id == "phase_runtime_exit":
            if not isinstance(rule.params, PhaseRuntimeExitParamsSpec):
                continue
            if rule.params.exit_price != "close":
                continue
            triggers.append(
                RuntimeExitTrigger(
                    rule_id=rule.rule_id,
                    component_id=rule.component_id,
                    exit_price=context.close,
                    exit_kind=rule.exit_kind,
                )
            )
            continue
        series = signals.get(rule.rule_id)
        if series is None:
            continue
        bar_index = context.bar_index
        if bar_index < 0 or bar_index >= len(series):
            continue
        if not bool(series.iloc[bar_index]):
            continue
        triggers.append(
            RuntimeExitTrigger(
                rule_id=rule.rule_id,
                component_id=rule.component_id,
                exit_price=context.close,
                exit_kind=rule.exit_kind,
            )
        )
    return triggers


def runtime_exit_candidate_type(exit_kind: RuntimeExitKind) -> str:
    if exit_kind == "protective_exit":
        return "runtime_protective"
    if exit_kind == "take_profit":
        return "runtime_take"
    return "runtime_close"
