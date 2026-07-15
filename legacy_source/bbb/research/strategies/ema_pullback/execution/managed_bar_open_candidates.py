"""Bar-open managed exit candidates from inherited ActiveManagementSnapshot."""

from __future__ import annotations

from typing import Literal

from research.strategies.ema_pullback.execution.exit_attribution import (
    _stop_hit_long,
    _stop_hit_short,
    fill_price_for_distance_exit,
)
from research.strategies.ema_pullback.consumer_roles import (
    EXIT_LAYER_RUNTIME_EXIT,
    EXIT_LAYER_STOP_RULE,
    EXIT_OWNER_EXIT_MANAGEMENT,
    ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT,
)
from research.strategies.ema_pullback.execution.managed_components.runtime_exit import (
    runtime_exit_candidate_type,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ActiveManagementSnapshot,
    ExitCandidate,
)
from research.strategies.ema_pullback.spec import RuntimeExitRuleSpec


def _runtime_rule(
    rules: tuple[RuntimeExitRuleSpec, ...],
    rule_id: str,
) -> RuntimeExitRuleSpec | None:
    for rule in rules:
        if rule.rule_id == rule_id:
            return rule
    return None


def collect_managed_bar_open_candidates(
    inherited: ActiveManagementSnapshot,
    *,
    bar_idx: int,
    direction: Literal["long", "short"],
    open_: float,
    high: float,
    low: float,
    close: float,
    runtime_exits: tuple[RuntimeExitRuleSpec, ...] = (),
) -> list[ExitCandidate]:
    out: list[ExitCandidate] = []

    stop = inherited.active_stop_price
    if stop is not None:
        if direction == "long":
            hit = _stop_hit_long(open_, high, low, stop, is_loss=True)
        else:
            hit = _stop_hit_short(open_, high, low, stop, is_loss=True)
        if hit:
            price = fill_price_for_distance_exit(
                direction,
                open_=open_,
                high=high,
                low=low,
                level=stop,
                is_loss=True,
            )
            out.append(
                ExitCandidate(
                    layer="exit_management",
                    rule_id=inherited.active_stop_rule_id,
                    component_id=inherited.active_stop_component_id,
                    price=price,
                    bar=bar_idx,
                    reason=f"active_stop:{inherited.active_stop_component_id}",
                    candidate_type="managed_stop",
                    attribution_layer=EXIT_LAYER_STOP_RULE,
                    exit_owner=EXIT_OWNER_EXIT_MANAGEMENT,
                )
            )

    for rule_id in inherited.active_runtime_exit_rules:
        rule = _runtime_rule(runtime_exits, rule_id)
        component_id = rule.component_id if rule is not None else None
        exit_kind = rule.exit_kind if rule is not None else "market_close"
        candidate_type = runtime_exit_candidate_type(exit_kind)
        out.append(
            ExitCandidate(
                layer="exit_management",
                rule_id=rule_id,
                component_id=component_id,
                price=close,
                bar=bar_idx,
                reason=f"runtime_exit:{exit_kind}",
                candidate_type=candidate_type,
                attribution_layer=EXIT_LAYER_RUNTIME_EXIT,
                exit_owner=EXIT_OWNER_EXIT_MANAGEMENT,
                exit_kind=exit_kind,
                role=ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT,
            )
        )

    return out
