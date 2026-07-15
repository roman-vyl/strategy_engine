from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from research.strategies.ema_pullback.consumer_roles import (
    EXIT_LAYER_RUNTIME_EXIT,
    EXIT_LAYER_STOP_RULE,
    EXIT_OWNER_EXIT_MANAGEMENT,
    ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT,
)
from research.strategies.ema_pullback.execution.managed_components.runtime_exit import (
    evaluate_runtime_exits,
    runtime_exit_candidate_type,
)
from research.strategies.ema_pullback.execution.managed_components.stop import (
    apply_tighten_only_stop,
    evaluate_stop_management,
    merge_stop_candidates,
)
from research.strategies.ema_pullback.execution.managed_components.take import (
    evaluate_take_management,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ActiveManagementSnapshot,
    ExitCandidate,
    ManagedExitContext,
    TradeManagementEvent,
    TradeRuntimeState,
    empty_active_management_snapshot,
)
from research.strategies.ema_pullback.spec import (
    RuntimeExitRuleSpec,
    StopManagementRuleSpec,
    TakeManagementRuleSpec,
)


@dataclass
class ManagementEvaluationResult:
    snapshot: ActiveManagementSnapshot
    events: list[TradeManagementEvent] = field(default_factory=list)
    candidates: list[ExitCandidate] = field(default_factory=list)


def _management_event(
    state: TradeRuntimeState,
    context: ManagedExitContext,
    *,
    event_type: str,
    rule_id: str | None,
    component_id: str | None,
    price: float | None = None,
    stop_price: float | None = None,
    metadata: dict[str, object] | None = None,
) -> TradeManagementEvent:
    return TradeManagementEvent(
        trade_id=state.trade_id,
        time_ms=context.time_ms,
        bar_index=context.bar_index,
        side=state.side,
        event_type=event_type,  # type: ignore[arg-type]
        from_phase=state.phase,
        to_phase=None,
        rule_id=rule_id,
        component_id=component_id,
        price=price,
        stop_price=stop_price,
        mfe_pct=state.mfe_pct,
        mae_pct=state.mae_pct,
        bars_in_trade=state.bars_in_trade,
        metadata=dict(metadata or {}),
    )


def _stop_changed(previous: float | None, new_stop: float) -> bool:
    if previous is None:
        return True
    return not math.isclose(previous, new_stop, rel_tol=0.0, abs_tol=1e-8)


def evaluate_management_layers(
    state: TradeRuntimeState,
    *,
    context: ManagedExitContext,
    stop_management: tuple[StopManagementRuleSpec, ...],
    take_management: tuple[TakeManagementRuleSpec, ...],
    runtime_exits: tuple[RuntimeExitRuleSpec, ...],
    previous: ActiveManagementSnapshot,
    atr_series_by_key: dict[tuple[str, int], pd.Series],
    runtime_exit_signals_by_rule_id: dict[str, pd.Series] | None = None,
) -> ManagementEvaluationResult:
    if not stop_management and not take_management and not runtime_exits:
        return ManagementEvaluationResult(
            snapshot=empty_active_management_snapshot(),
            events=[],
            candidates=[],
        )

    events: list[TradeManagementEvent] = []
    candidates: list[ExitCandidate] = []
    snapshot = previous

    stop_candidates = evaluate_stop_management(
        stop_management,
        context=context,
        atr_series_by_key=atr_series_by_key,
    )
    merged_stop = merge_stop_candidates(stop_candidates, side=context.side)
    if merged_stop is not None:
        tightened = apply_tighten_only_stop(
            previous.active_stop_price,
            merged_stop.stop_price,
            side=context.side,
        )
        if _stop_changed(previous.active_stop_price, tightened):
            snapshot = ActiveManagementSnapshot(
                active_stop_price=tightened,
                active_stop_rule_id=merged_stop.rule_id,
                active_stop_component_id=merged_stop.component_id,
                active_take_profile=snapshot.active_take_profile,
                active_take_rule_id=snapshot.active_take_rule_id,
                active_take_component_id=snapshot.active_take_component_id,
                active_runtime_exit_rules=snapshot.active_runtime_exit_rules,
            )
            events.append(
                _management_event(
                    state,
                    context,
                    event_type="active_stop_updated",
                    rule_id=merged_stop.rule_id,
                    component_id=merged_stop.component_id,
                    price=tightened,
                    stop_price=tightened,
                    metadata={
                        "merged_stop_prices": {
                            item.rule_id: item.stop_price for item in stop_candidates
                        },
                        "effective_from_bar": context.bar_index + 1,
                    },
                )
            )
        candidates.append(
            ExitCandidate(
                layer="exit_management",
                rule_id=merged_stop.rule_id,
                component_id=merged_stop.component_id,
                price=tightened,
                bar=context.bar_index,
                reason=f"active_stop:{merged_stop.component_id}",
                candidate_type="managed_stop",
                attribution_layer=EXIT_LAYER_STOP_RULE,
                exit_owner=EXIT_OWNER_EXIT_MANAGEMENT,
            )
        )

    take_selection = evaluate_take_management(take_management, context=context)
    if (
        take_selection is not None
        and take_selection.profile != previous.active_take_profile
    ):
        metadata: dict[str, object] = {
            "take_profile": take_selection.profile,
            "effective_from_bar": context.bar_index + 1,
        }
        snapshot = ActiveManagementSnapshot(
            active_stop_price=snapshot.active_stop_price,
            active_stop_rule_id=snapshot.active_stop_rule_id,
            active_stop_component_id=snapshot.active_stop_component_id,
            active_take_profile=take_selection.profile,
            active_take_rule_id=take_selection.rule_id,
            active_take_component_id=take_selection.component_id,
            active_runtime_exit_rules=snapshot.active_runtime_exit_rules,
        )
        events.append(
            _management_event(
                state,
                context,
                event_type="active_take_updated",
                rule_id=take_selection.rule_id,
                component_id=take_selection.component_id,
                price=None,
                stop_price=snapshot.active_stop_price,
                metadata=metadata,
            )
        )

    runtime_triggers = evaluate_runtime_exits(
        runtime_exits,
        context=context,
        signal_series_by_rule_id=runtime_exit_signals_by_rule_id,
    )
    armed_rule_ids = tuple(trigger.rule_id for trigger in runtime_triggers)
    if armed_rule_ids != previous.active_runtime_exit_rules:
        snapshot = ActiveManagementSnapshot(
            active_stop_price=snapshot.active_stop_price,
            active_stop_rule_id=snapshot.active_stop_rule_id,
            active_stop_component_id=snapshot.active_stop_component_id,
            active_take_profile=snapshot.active_take_profile,
            active_take_rule_id=snapshot.active_take_rule_id,
            active_take_component_id=snapshot.active_take_component_id,
            active_runtime_exit_rules=armed_rule_ids,
        )

    for trigger in runtime_triggers:
        candidate_type = runtime_exit_candidate_type(trigger.exit_kind)
        events.append(
            _management_event(
                state,
                context,
                event_type="runtime_exit_triggered",
                rule_id=trigger.rule_id,
                component_id=trigger.component_id,
                price=trigger.exit_price,
                stop_price=snapshot.active_stop_price,
                metadata={
                    "exit_price": "close",
                    "effective_from_bar": context.bar_index + 1,
                    "exit_kind": trigger.exit_kind,
                    "role": trigger.role,
                    "attribution_layer": EXIT_LAYER_RUNTIME_EXIT,
                    "exit_owner": EXIT_OWNER_EXIT_MANAGEMENT,
                    "phase": context.phase,
                },
            )
        )
        candidates.append(
            ExitCandidate(
                layer="exit_management",
                rule_id=trigger.rule_id,
                component_id=trigger.component_id,
                price=trigger.exit_price,
                bar=context.bar_index,
                reason=f"runtime_exit:{trigger.exit_kind}",
                candidate_type=candidate_type,
                attribution_layer=EXIT_LAYER_RUNTIME_EXIT,
                exit_owner=EXIT_OWNER_EXIT_MANAGEMENT,
                exit_kind=trigger.exit_kind,
                role=trigger.role,
            )
        )

    return ManagementEvaluationResult(snapshot=snapshot, events=events, candidates=candidates)
