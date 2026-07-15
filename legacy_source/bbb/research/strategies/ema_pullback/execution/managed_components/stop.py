from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from research.strategies.ema_pullback.execution.managed_components.activation import (
    phase_at_least_met,
)
from research.strategies.ema_pullback.execution.managed_components.atr import (
    atr_value_at_bar,
)
from research.strategies.ema_pullback.execution.trade_runtime import ManagedExitContext
from research.strategies.ema_pullback.spec import (
    BreakEvenStopParamsSpec,
    LockProfitStopParamsSpec,
    StopManagementRuleSpec,
)

Side = Literal["long", "short"]


@dataclass(frozen=True)
class StopCandidate:
    stop_price: float
    rule_id: str
    component_id: str


def apply_tighten_only_stop(
    previous: float | None,
    candidate: float,
    *,
    side: Side,
) -> float:
    if previous is None:
        return candidate
    if side == "long":
        return max(previous, candidate)
    return min(previous, candidate)


def merge_stop_candidates(
    candidates: list[StopCandidate],
    *,
    side: Side,
) -> StopCandidate | None:
    if not candidates:
        return None
    if side == "long":
        return max(candidates, key=lambda item: item.stop_price)
    return min(candidates, key=lambda item: item.stop_price)


def evaluate_break_even_stop(
    rule: StopManagementRuleSpec,
    *,
    context: ManagedExitContext,
    atr_series_by_key: dict[tuple[str, int], pd.Series],
) -> float | None:
    if rule.component_id != "break_even_stop":
        return None
    if not phase_at_least_met(context.phase, rule.activate_when.phase_at_least):
        return None
    if not isinstance(rule.params, BreakEvenStopParamsSpec):
        return None

    params = rule.params
    buffer: float | None
    if params.buffer_type == "none":
        buffer = params.buffer
    else:
        atr_value = atr_value_at_bar(
            bar_index=context.bar_index,
            atr_period=params.atr_period,
            atr=params.atr,
            atr_series_by_key=atr_series_by_key,
        )
        if atr_value is None:
            return None
        buffer = params.buffer_atr * atr_value

    if context.side == "long":
        return context.entry_price + buffer
    return context.entry_price - buffer


def evaluate_lock_profit_stop(
    rule: StopManagementRuleSpec,
    *,
    context: ManagedExitContext,
    atr_series_by_key: dict[tuple[str, int], pd.Series],
) -> float | None:
    if rule.component_id != "lock_profit_stop":
        return None
    if not phase_at_least_met(context.phase, rule.activate_when.phase_at_least):
        return None
    if not isinstance(rule.params, LockProfitStopParamsSpec):
        return None

    params = rule.params
    atr_value = atr_value_at_bar(
        bar_index=context.bar_index,
        atr_period=params.atr_period,
        atr=params.atr,
        atr_series_by_key=atr_series_by_key,
    )
    if atr_value is None:
        return None

    offset = params.lock_atr * atr_value
    if context.side == "long":
        return context.entry_price + offset
    return context.entry_price - offset


def evaluate_stop_management(
    rules: tuple[StopManagementRuleSpec, ...],
    *,
    context: ManagedExitContext,
    atr_series_by_key: dict[tuple[str, int], pd.Series],
) -> list[StopCandidate]:
    candidates: list[StopCandidate] = []
    for rule in rules:
        raw_price: float | None
        if rule.component_id == "break_even_stop":
            raw_price = evaluate_break_even_stop(
                rule, context=context, atr_series_by_key=atr_series_by_key
            )
        elif rule.component_id == "lock_profit_stop":
            raw_price = evaluate_lock_profit_stop(
                rule, context=context, atr_series_by_key=atr_series_by_key
            )
        else:
            continue
        if raw_price is None or not math.isfinite(raw_price):
            continue
        candidates.append(
            StopCandidate(
                stop_price=raw_price,
                rule_id=rule.rule_id,
                component_id=rule.component_id,
            )
        )
    return candidates
