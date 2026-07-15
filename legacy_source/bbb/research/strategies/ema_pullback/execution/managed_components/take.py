from __future__ import annotations

from dataclasses import dataclass

from research.strategies.ema_pullback.execution.managed_components.activation import (
    phase_at_least_met,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ACTIVE_TAKE_PROFILE_INITIAL,
    ManagedExitContext,
)
from research.strategies.ema_pullback.spec import TakeManagementRuleSpec


ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP = "disable_initial_tp"

_DEPRECATED_ACTION_ALIASES = {
    "disable_fixed_tp": ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP,
}


def normalize_take_profile_action(action: str) -> str:
    return _DEPRECATED_ACTION_ALIASES.get(action, action)


@dataclass(frozen=True)
class TakeProfileSelection:
    profile: str
    rule_id: str
    component_id: str


def take_profile_descriptor(action: str) -> str:
    normalized = normalize_take_profile_action(action)
    if normalized == "keep_initial":
        return ACTIVE_TAKE_PROFILE_INITIAL
    if normalized == ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP:
        return ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP
    return normalized


def evaluate_take_management(
    rules: tuple[TakeManagementRuleSpec, ...],
    *,
    context: ManagedExitContext,
) -> TakeProfileSelection | None:
    selection: TakeProfileSelection | None = None
    for rule in rules:
        if rule.component_id != "take_profile_switch":
            continue
        if not phase_at_least_met(context.phase, rule.activate_when.phase_at_least):
            continue
        params = rule.params
        selection = TakeProfileSelection(
            profile=take_profile_descriptor(params.action),
            rule_id=rule.rule_id,
            component_id=rule.component_id,
        )
    return selection
