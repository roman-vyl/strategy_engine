"""Trade-management runtime: diagnostic replay and managed bar-by-bar loop.

Diagnostic-only helpers rebuild phase state from closed trade records without
feeding back into portfolio execution.

Managed mode (``run_managed_exit_runtime``) runs a bar-by-bar loop over each
open trade window inside the research execution path. Slice 2+ skeleton: phase
rules and ``ActiveManagementSnapshot`` only; behavior-changing management
evaluators and arbitration wire in later slices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from research.strategies.ema_pullback.phase_rule_conditions.registry import (
    PhaseRuleEvaluationContext,
    evaluate_phase_rule_condition,
)
from research.strategies.ema_pullback.spec import (
    ExitManagementMode,
    PhaseRuleSpec,
    RuntimeExitRuleSpec,
    StopManagementRuleSpec,
    TakeManagementRuleSpec,
    TRADE_MANAGEMENT_PHASES,
)

TradePhase = Literal["initial_risk", "proven", "protected", "runner", "exhaustion"]
TradeRuntimeEventType = Literal[
    "phase_changed",
    "active_stop_updated",
    "active_take_updated",
    "runtime_exit_triggered",
    "runtime_exit_executed",
    "exit_rule_triggered",
    "exit_executed",
]

MANAGED_RUNTIME_EVENT_TYPES: tuple[TradeRuntimeEventType, ...] = (
    "phase_changed",
    "active_stop_updated",
    "active_take_updated",
    "runtime_exit_triggered",
    "runtime_exit_executed",
    "exit_rule_triggered",
    "exit_executed",
)

MANAGED_ACTIVE_LAYER_EVENT_TYPES: frozenset[TradeRuntimeEventType] = frozenset(
    {
        "active_stop_updated",
        "active_take_updated",
        "runtime_exit_triggered",
    }
)

ACTIVE_TAKE_PROFILE_INITIAL = "initial"
ACTIVE_TAKE_PROFILE_NONE = "none"

ExitCandidateLayer = Literal["exit_policy", "exit_management"]


@dataclass
class TradeRuntimeState:
    trade_id: str
    side: Literal["long", "short"]
    entry_idx: int
    entry_time_ms: int
    entry_price: float
    bars_in_trade: int
    phase: TradePhase
    max_phase_reached: str
    best_price: float
    worst_price: float
    mfe_price: float
    mfe_pct: float
    mae_price: float
    mae_pct: float
    active_stop_price: float | None
    active_stop_source: str | None
    initial_stop_price: float | None
    initial_take_profit_price: float | None
    locked_exit_profile: str | None


@dataclass(frozen=True)
class TradeManagementEvent:
    trade_id: str
    time_ms: int
    bar_index: int
    side: str
    event_type: TradeRuntimeEventType
    from_phase: str | None
    to_phase: str | None
    rule_id: str | None
    component_id: str | None
    price: float | None
    stop_price: float | None
    mfe_pct: float
    mae_pct: float
    bars_in_trade: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class TradeRuntimeResult:
    states_by_trade_id: dict[str, TradeRuntimeState]
    events: list[TradeManagementEvent]


@dataclass(frozen=True)
class ActiveManagementSnapshot:
    active_stop_price: float | None = None
    active_stop_rule_id: str | None = None
    active_stop_component_id: str | None = None
    active_take_profile: str = ACTIVE_TAKE_PROFILE_INITIAL
    active_take_rule_id: str | None = None
    active_take_component_id: str | None = None
    active_runtime_exit_rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExitCandidate:
    layer: ExitCandidateLayer
    rule_id: str | None
    component_id: str | None
    price: float
    bar: int
    reason: str
    candidate_type: str | None = None
    attribution_layer: str | None = None
    exit_owner: str | None = None
    exit_kind: str | None = None
    role: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManagedExitContext:
    bar_index: int
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    side: Literal["long", "short"]
    entry_price: float
    phase: TradePhase
    mfe_pct: float
    mae_pct: float
    bars_in_trade: int
    feature_refs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagedTradeRuntimeState:
    runtime: TradeRuntimeState
    active_management: ActiveManagementSnapshot
    exit_candidates: list[ExitCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class ManagedTradeRuntimeResult:
    states_by_trade_id: dict[str, ManagedTradeRuntimeState]
    events: list[TradeManagementEvent]


def empty_active_management_snapshot() -> ActiveManagementSnapshot:
    return ActiveManagementSnapshot()


def is_managed_exit_mode(mode: ExitManagementMode | None) -> bool:
    return mode == "managed"


def has_behavior_changing_management_rules(
    *,
    stop_management: tuple[StopManagementRuleSpec, ...],
    take_management: tuple[TakeManagementRuleSpec, ...],
    runtime_exits: tuple[RuntimeExitRuleSpec, ...],
) -> bool:
    return bool(stop_management or take_management or runtime_exits)


_PHASE_MILESTONE_FIELDS = {
    "proven": ("bars_to_proven", "mfe_at_proven_pct"),
    "protected": ("bars_to_protected", "mfe_at_protected_pct"),
    "runner": ("bars_to_runner", "mfe_at_runner_pct"),
}


def _index_to_time_ms(index: pd.Index, idx: int) -> int:
    value = index[idx]
    if isinstance(value, pd.Timestamp):
        return int(value.value // 1_000_000)
    return int(idx)


def _phase_rank(phase: str) -> int:
    return TRADE_MANAGEMENT_PHASES.index(phase)


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _initial_state(
    trade: dict[str, Any],
    *,
    entry_idx: int,
    index: pd.Index,
) -> TradeRuntimeState | None:
    side = str(trade.get("direction") or "")
    if side not in {"long", "short"}:
        return None
    entry_price = _finite_float(trade.get("entry_price"))
    if entry_price is None or entry_price <= 0:
        return None
    trade_id = str(trade.get("trade_id") or f"{side}:{entry_idx}")
    return TradeRuntimeState(
        trade_id=trade_id,
        side=side,  # type: ignore[arg-type]
        entry_idx=entry_idx,
        entry_time_ms=_index_to_time_ms(index, entry_idx),
        entry_price=entry_price,
        bars_in_trade=0,
        phase="initial_risk",
        max_phase_reached="initial_risk",
        best_price=entry_price,
        worst_price=entry_price,
        mfe_price=entry_price,
        mfe_pct=0.0,
        mae_price=entry_price,
        mae_pct=0.0,
        active_stop_price=None,
        active_stop_source=None,
        initial_stop_price=None,
        initial_take_profit_price=None,
        locked_exit_profile=trade.get("active_exit_profile") or trade.get("entry_profile"),
    )


def update_trade_runtime_state(
    state: TradeRuntimeState,
    *,
    bar_index: int,
    high: float,
    low: float,
) -> None:
    """Update side-aware price extremes for one actual in-trade bar."""

    state.bars_in_trade = bar_index - state.entry_idx + 1
    if state.side == "long":
        state.best_price = max(state.best_price, high)
        state.worst_price = min(state.worst_price, low)
        state.mfe_price = state.best_price
        state.mae_price = state.worst_price
        state.mfe_pct = (state.best_price - state.entry_price) / state.entry_price
        state.mae_pct = (state.entry_price - state.worst_price) / state.entry_price
        return

    state.best_price = min(state.best_price, low)
    state.worst_price = max(state.worst_price, high)
    state.mfe_price = state.best_price
    state.mae_price = state.worst_price
    state.mfe_pct = (state.entry_price - state.best_price) / state.entry_price
    state.mae_pct = (state.worst_price - state.entry_price) / state.entry_price


def _resolve_eval_context(
    eval_context: PhaseRuleEvaluationContext | None,
    atr_series_by_key: dict[tuple[str, int], pd.Series] | None,
) -> PhaseRuleEvaluationContext:
    if eval_context is not None:
        return eval_context
    return PhaseRuleEvaluationContext(
        atr_series_by_key=atr_series_by_key or {},
        adx_dmi_series_by_key={},
    )


def evaluate_phase_rules(
    state: TradeRuntimeState,
    phase_rules: tuple[PhaseRuleSpec, ...],
    *,
    bar_index: int,
    time_ms: int,
    eval_context: PhaseRuleEvaluationContext | None = None,
    atr_series_by_key: dict[tuple[str, int], pd.Series] | None = None,
) -> list[TradeManagementEvent]:
    """Apply ordered monotonic phase rules to one state on one bar."""

    events: list[TradeManagementEvent] = []
    context = _resolve_eval_context(eval_context, atr_series_by_key)
    for rule in phase_rules:
        if _phase_rank(rule.to_phase) <= _phase_rank(state.phase):
            continue
        result = evaluate_phase_rule_condition(
            state,
            rule.condition,
            bar_index=bar_index,
            eval_context=context,
        )
        if not result.met:
            continue
        from_phase = state.phase
        state.phase = rule.to_phase  # type: ignore[assignment]
        if _phase_rank(state.phase) > _phase_rank(state.max_phase_reached):
            state.max_phase_reached = state.phase
        metadata: dict[str, Any] = {
            "condition_component_id": rule.condition.component_id,
            **result.diagnostics,
        }
        events.append(
            TradeManagementEvent(
                trade_id=state.trade_id,
                time_ms=time_ms,
                bar_index=bar_index,
                side=state.side,
                event_type="phase_changed",
                from_phase=from_phase,
                to_phase=state.phase,
                rule_id=rule.rule_id,
                component_id=rule.condition.component_id,
                price=state.mfe_price,
                stop_price=state.active_stop_price,
                mfe_pct=state.mfe_pct,
                mae_pct=state.mae_pct,
                bars_in_trade=state.bars_in_trade,
                metadata=metadata,
            )
        )
    return events


def _build_managed_exit_context(
    state: TradeRuntimeState,
    *,
    bar_index: int,
    time_ms: int,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> ManagedExitContext:
    return ManagedExitContext(
        bar_index=bar_index,
        time_ms=time_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        side=state.side,
        entry_price=state.entry_price,
        phase=state.phase,
        mfe_pct=state.mfe_pct,
        mae_pct=state.mae_pct,
        bars_in_trade=state.bars_in_trade,
    )


def _recompute_active_management_snapshot(
    state: TradeRuntimeState,
    *,
    context: ManagedExitContext,
    stop_management: tuple[StopManagementRuleSpec, ...],
    take_management: tuple[TakeManagementRuleSpec, ...],
    runtime_exits: tuple[RuntimeExitRuleSpec, ...],
    previous: ActiveManagementSnapshot,
    atr_series_by_key: dict[tuple[str, int], pd.Series],
) -> tuple[ActiveManagementSnapshot, list[TradeManagementEvent], list[ExitCandidate]]:
    from research.strategies.ema_pullback.execution.managed_components.snapshot import (
        evaluate_management_layers,
    )

    result = evaluate_management_layers(
        state,
        context=context,
        stop_management=stop_management,
        take_management=take_management,
        runtime_exits=runtime_exits,
        previous=previous,
        atr_series_by_key=atr_series_by_key,
    )
    return result.snapshot, result.events, result.candidates


def _exit_executed_event(
    *,
    state: TradeRuntimeState,
    trade: dict[str, Any],
    exit_idx: int,
    index: pd.Index,
) -> TradeManagementEvent:
    exit_price = _finite_float(trade.get("exit_price"))
    return TradeManagementEvent(
        trade_id=state.trade_id,
        time_ms=_index_to_time_ms(index, exit_idx),
        bar_index=exit_idx,
        side=state.side,
        event_type="exit_executed",
        from_phase=state.phase,
        to_phase=None,
        rule_id=str(trade.get("exit_rule_id") or trade.get("exit_instance_id") or "") or None,
        component_id=trade.get("exit_component_id"),
        price=exit_price,
        stop_price=state.active_stop_price,
        mfe_pct=state.mfe_pct,
        mae_pct=state.mae_pct,
        bars_in_trade=state.bars_in_trade,
        metadata={"exit_reason": trade.get("exit_reason")},
    )


def run_managed_exit_runtime(
    *,
    trade_records: list[dict[str, Any]],
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    phase_rules: tuple[PhaseRuleSpec, ...],
    stop_management: tuple[StopManagementRuleSpec, ...] = (),
    take_management: tuple[TakeManagementRuleSpec, ...] = (),
    runtime_exits: tuple[RuntimeExitRuleSpec, ...] = (),
    eval_context: PhaseRuleEvaluationContext | None = None,
    atr_series_by_key: dict[tuple[str, int], pd.Series] | None = None,
) -> ManagedTradeRuntimeResult:
    """Bar-by-bar managed runtime entry point (research execution path).

    Slice 2: updates phase state and neutral ``ActiveManagementSnapshot`` when
    management arrays are empty. Does not create managed exit candidates or
    change baseline exit selection — trades must already be closed by the
    existing execution path (vectorbt / legacy combiner).
    """

    index = close.index
    states: dict[str, ManagedTradeRuntimeState] = {}
    events: list[TradeManagementEvent] = []
    context = _resolve_eval_context(eval_context, atr_series_by_key)
    atr_for_management = context.atr_series_by_key

    for trade in trade_records:
        if trade.get("status") != "closed":
            continue
        try:
            entry_idx = int(trade.get("entry_idx"))
            exit_idx = int(trade.get("exit_idx"))
        except (TypeError, ValueError):
            continue
        if entry_idx < 0 or exit_idx < entry_idx or exit_idx >= len(close):
            continue
        runtime_state = _initial_state(trade, entry_idx=entry_idx, index=index)
        if runtime_state is None:
            continue

        active_management = empty_active_management_snapshot()
        trade_candidates: list[ExitCandidate] = []
        for bar_idx in range(entry_idx, exit_idx + 1):
            open_value = _finite_float(open_.iloc[bar_idx])
            high_value = _finite_float(high.iloc[bar_idx])
            low_value = _finite_float(low.iloc[bar_idx])
            close_value = _finite_float(close.iloc[bar_idx])
            if (
                open_value is None
                or high_value is None
                or low_value is None
                or close_value is None
            ):
                continue
            update_trade_runtime_state(
                runtime_state,
                bar_index=bar_idx,
                high=high_value,
                low=low_value,
            )
            time_ms = _index_to_time_ms(index, bar_idx)
            events.extend(
                evaluate_phase_rules(
                    runtime_state,
                    phase_rules,
                    bar_index=bar_idx,
                    time_ms=time_ms,
                    eval_context=context,
                )
            )
            managed_context = _build_managed_exit_context(
                runtime_state,
                bar_index=bar_idx,
                time_ms=time_ms,
                open_=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
            )
            active_management, layer_events, layer_candidates = _recompute_active_management_snapshot(
                runtime_state,
                context=managed_context,
                stop_management=stop_management,
                take_management=take_management,
                runtime_exits=runtime_exits,
                previous=active_management,
                atr_series_by_key=atr_for_management,
            )
            events.extend(layer_events)
            trade_candidates.extend(layer_candidates)

        events.append(
            _exit_executed_event(
                state=runtime_state,
                trade=trade,
                exit_idx=exit_idx,
                index=index,
            )
        )
        states[runtime_state.trade_id] = ManagedTradeRuntimeState(
            runtime=runtime_state,
            active_management=active_management,
            exit_candidates=trade_candidates,
        )

    return ManagedTradeRuntimeResult(states_by_trade_id=states, events=events)


def managed_trade_management_block_for_trade(
    record: dict[str, Any],
    managed_state: ManagedTradeRuntimeState,
    events: list[TradeManagementEvent],
) -> dict[str, Any]:
    block = trade_management_block_for_trade(
        record,
        managed_state.runtime,
        events,
    )
    snapshot = managed_state.active_management
    block["active_stop_at_exit"] = snapshot.active_stop_price
    block["active_take_at_exit"] = snapshot.active_take_profile
    block["active_stop_component_id"] = snapshot.active_stop_component_id
    block["active_take_component_id"] = snapshot.active_take_component_id

    exit_layer = record.get("exit_layer")
    if isinstance(exit_layer, str) and exit_layer:
        block["exit_layer"] = exit_layer
    exit_owner = record.get("exit_owner")
    if isinstance(exit_owner, str) and exit_owner:
        block["exit_owner"] = exit_owner

    exit_executed = next(
        (event for event in reversed(events) if event.event_type == "exit_executed"),
        None,
    )
    if exit_executed is not None:
        meta_layer = exit_executed.metadata.get("exit_layer")
        if isinstance(meta_layer, str) and meta_layer:
            block["exit_layer"] = meta_layer
        meta_owner = exit_executed.metadata.get("exit_owner")
        if isinstance(meta_owner, str) and meta_owner:
            block["exit_owner"] = meta_owner
        if exit_executed.rule_id:
            block["exit_rule_id"] = exit_executed.rule_id
        if exit_executed.component_id:
            block["exit_component_id"] = exit_executed.component_id

    candidate_type = record.get("managed_exit_candidate_type")
    if isinstance(candidate_type, str) and candidate_type:
        block["exit_candidate_type"] = candidate_type

    block["managed_events"] = [_event_payload(event) for event in events]
    return block


def apply_managed_trade_management_diagnostics(
    trade_records: list[dict[str, Any]],
    result: ManagedTradeRuntimeResult,
) -> None:
    events_by_trade = _events_by_trade_id(result)
    for record in trade_records:
        if record.get("status") != "closed":
            continue
        trade_id = str(record.get("trade_id") or "")
        managed_state = result.states_by_trade_id.get(trade_id)
        if managed_state is None:
            continue
        record["trade_management"] = managed_trade_management_block_for_trade(
            record,
            managed_state,
            events_by_trade.get(trade_id, ()),
        )


def build_trade_runtime_diagnostics(
    *,
    trade_records: list[dict[str, Any]],
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    phase_rules: tuple[PhaseRuleSpec, ...],
    eval_context: PhaseRuleEvaluationContext | None = None,
    atr_series_by_key: dict[tuple[str, int], pd.Series] | None = None,
) -> TradeRuntimeResult:
    """Build diagnostic runtime state from actual closed trade windows only."""

    index = close.index
    states: dict[str, TradeRuntimeState] = {}
    events: list[TradeManagementEvent] = []
    context = _resolve_eval_context(eval_context, atr_series_by_key)

    for trade in trade_records:
        if trade.get("status") != "closed":
            continue
        try:
            entry_idx = int(trade.get("entry_idx"))
            exit_idx = int(trade.get("exit_idx"))
        except (TypeError, ValueError):
            continue
        if entry_idx < 0 or exit_idx < entry_idx or exit_idx >= len(close):
            continue
        state = _initial_state(trade, entry_idx=entry_idx, index=index)
        if state is None:
            continue

        for bar_idx in range(entry_idx, exit_idx + 1):
            high_value = _finite_float(high.iloc[bar_idx])
            low_value = _finite_float(low.iloc[bar_idx])
            if high_value is None or low_value is None:
                continue
            update_trade_runtime_state(
                state,
                bar_index=bar_idx,
                high=high_value,
                low=low_value,
            )
            events.extend(
                evaluate_phase_rules(
                    state,
                    phase_rules,
                    bar_index=bar_idx,
                    time_ms=_index_to_time_ms(index, bar_idx),
                    eval_context=context,
                )
            )

        events.append(
            _exit_executed_event(
                state=state,
                trade=trade,
                exit_idx=exit_idx,
                index=index,
            )
        )
        states[state.trade_id] = state

    return TradeRuntimeResult(states_by_trade_id=states, events=events)


def _event_payload(event: TradeManagementEvent) -> dict[str, Any]:
    return {
        "trade_id": event.trade_id,
        "time_ms": event.time_ms,
        "bar_index": event.bar_index,
        "side": event.side,
        "event_type": event.event_type,
        "from_phase": event.from_phase,
        "to_phase": event.to_phase,
        "rule_id": event.rule_id,
        "component_id": event.component_id,
        "price": event.price,
        "stop_price": event.stop_price,
        "mfe_pct": event.mfe_pct,
        "mae_pct": event.mae_pct,
        "bars_in_trade": event.bars_in_trade,
        "metadata": dict(event.metadata),
    }


def trade_management_events_payload(
    result: TradeRuntimeResult | ManagedTradeRuntimeResult,
) -> list[dict[str, Any]]:
    ordered = sorted(enumerate(result.events), key=lambda item: (item[1].bar_index, item[0]))
    return [_event_payload(event) for _order, event in ordered]


def _events_by_trade_id(
    result: TradeRuntimeResult | ManagedTradeRuntimeResult,
) -> dict[str, list[TradeManagementEvent]]:
    out: dict[str, list[TradeManagementEvent]] = {}
    for event in result.events:
        out.setdefault(event.trade_id, []).append(event)
    return out


def _exit_layer(record: dict[str, Any]) -> str | None:
    kind = record.get("exit_kind")
    if isinstance(kind, str) and kind:
        return kind
    reason = str(record.get("exit_reason") or "")
    if ":" in reason:
        return reason.split(":", 1)[0]
    return reason or None


def _capture_fields(record: dict[str, Any], state: TradeRuntimeState) -> tuple[float | None, float | None]:
    exit_price = _finite_float(record.get("exit_price"))
    if exit_price is None or state.entry_price <= 0:
        return None, None
    if state.side == "long":
        captured_pct = (exit_price - state.entry_price) / state.entry_price
    else:
        captured_pct = (state.entry_price - exit_price) / state.entry_price
    giveback_pct = max(0.0, state.mfe_pct - captured_pct)
    capture_ratio = captured_pct / state.mfe_pct if state.mfe_pct > 0 else None
    return capture_ratio, giveback_pct


def trade_management_block_for_trade(
    record: dict[str, Any],
    state: TradeRuntimeState,
    events: list[TradeManagementEvent],
) -> dict[str, Any]:
    capture_ratio, giveback_pct = _capture_fields(record, state)
    from research.strategies.ema_pullback.consumer_roles import exit_owner_for_layer

    raw_layer = record.get("exit_layer")
    if isinstance(raw_layer, str) and raw_layer.startswith("exit_management."):
        exit_layer_value = raw_layer
    else:
        exit_layer_value = _exit_layer(record)
    exit_owner_value = record.get("exit_owner")
    if not isinstance(exit_owner_value, str) or not exit_owner_value:
        exit_owner_value = (
            exit_owner_for_layer(exit_layer_value)
            if isinstance(exit_layer_value, str)
            else None
        )
    block: dict[str, Any] = {
        "phase_at_exit": state.phase,
        "max_phase_reached": state.max_phase_reached,
        "active_stop_source_at_exit": state.active_stop_source,
        "active_stop_price_at_exit": state.active_stop_price,
        "exit_layer": exit_layer_value,
        "exit_owner": exit_owner_value,
        "exit_rule_id": record.get("exit_rule_id") or record.get("exit_instance_id"),
        "exit_component_id": record.get("exit_component_id"),
        "best_price_before_exit": state.best_price,
        "giveback_from_best_price_pct": giveback_pct,
        "capture_ratio": capture_ratio,
        "mfe_pct": state.mfe_pct,
    }
    phase_events = [event for event in events if event.event_type == "phase_changed"]
    by_phase: dict[str, TradeManagementEvent] = {}
    for event in phase_events:
        if event.to_phase is not None and event.to_phase not in by_phase:
            by_phase[event.to_phase] = event
    for phase, (bars_field, mfe_field) in _PHASE_MILESTONE_FIELDS.items():
        event = by_phase.get(phase)
        block[bars_field] = None if event is None else event.bars_in_trade
        block[mfe_field] = None if event is None else event.mfe_pct
    return block


def apply_trade_management_diagnostics(
    trade_records: list[dict[str, Any]],
    result: TradeRuntimeResult,
) -> None:
    events_by_trade = _events_by_trade_id(result)
    for record in trade_records:
        if record.get("status") != "closed":
            continue
        trade_id = str(record.get("trade_id") or "")
        state = result.states_by_trade_id.get(trade_id)
        if state is None:
            continue
        record["trade_management"] = trade_management_block_for_trade(
            record,
            state,
            events_by_trade.get(trade_id, ()),
        )


def _finite_values(records: list[dict[str, Any]], path: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for record in records:
        current: Any = record
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        value = _finite_float(current)
        if value is not None:
            values.append(value)
    return values


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _profit_factor(records: list[dict[str, Any]]) -> float | None:
    pnls = [float(record.get("pnl") or 0.0) for record in records]
    gross_profit = sum(value for value in pnls if value > 0.0)
    gross_loss = abs(sum(value for value in pnls if value < 0.0))
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def _exit_reason_mix(records: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        reason = str(record.get("exit_reason") or "unknown")
        out[reason] = out.get(reason, 0) + 1
    return out


def _exit_layer_mix(records: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        tm = record.get("trade_management")
        layer = tm.get("exit_layer") if isinstance(tm, dict) else _exit_layer(record)
        key = str(layer or "unknown")
        out[key] = out.get(key, 0) + 1
    return out


def _phase_bucket(records: list[dict[str, Any]], *, all_count: int) -> dict[str, Any]:
    pnl_values = [float(record.get("pnl") or 0.0) for record in records]
    mfe = _finite_values(records, ("trade_management", "mfe_pct"))
    giveback = _finite_values(records, ("trade_management", "giveback_from_best_price_pct"))
    capture = _finite_values(records, ("trade_management", "capture_ratio"))
    wins = sum(1 for value in pnl_values if value > 0.0)
    count = len(records)
    return {
        "trade_count": count,
        "share_of_all_trades": (count / all_count) if all_count else None,
        "pnl": sum(pnl_values),
        "profit_factor": _profit_factor(records),
        "win_rate": (wins / count) if count else None,
        "avg_mfe_pct": _avg(mfe),
        "p75_mfe_pct": _percentile(mfe, 0.75),
        "p90_mfe_pct": _percentile(mfe, 0.90),
        "avg_giveback_pct": _avg(giveback),
        "median_giveback_pct": _median(giveback),
        "avg_capture_ratio": _avg(capture),
        "median_capture_ratio": _median(capture),
        "exit_reason_mix": _exit_reason_mix(records),
    }


def _reached_phase(record: dict[str, Any], phase: str) -> bool:
    tm = record.get("trade_management")
    if not isinstance(tm, dict):
        return False
    reached = tm.get("max_phase_reached")
    if not isinstance(reached, str) or reached not in TRADE_MANAGEMENT_PHASES:
        return False
    return _phase_rank(reached) >= _phase_rank(phase)


def _summary_for_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    giveback = _finite_values(records, ("trade_management", "giveback_from_best_price_pct"))
    capture = _finite_values(records, ("trade_management", "capture_ratio"))
    return {
        "trade_count": len(records),
        "avg_capture_ratio": _avg(capture),
        "median_capture_ratio": _median(capture),
        "avg_giveback_pct": _avg(giveback),
        "median_giveback_pct": _median(giveback),
        "exit_layer_mix": _exit_layer_mix(records),
        "exit_reason_mix": _exit_reason_mix(records),
    }


def build_trade_management_summary(
    trade_records: list[dict[str, Any]],
    *,
    managed_mode: bool = False,
) -> dict[str, Any] | None:
    closed = [
        record
        for record in trade_records
        if record.get("status") == "closed" and isinstance(record.get("trade_management"), dict)
    ]
    if not closed:
        return None

    by_phase: dict[str, Any] = {}
    for phase in TRADE_MANAGEMENT_PHASES:
        bucket = [
            record
            for record in closed
            if record["trade_management"].get("max_phase_reached") == phase
        ]
        by_phase[phase] = _phase_bucket(bucket, all_count=len(closed))

    phase_transition_counts: dict[str, int] = {}
    for record in closed:
        reached = record["trade_management"].get("max_phase_reached")
        if isinstance(reached, str):
            for phase in TRADE_MANAGEMENT_PHASES[1:]:
                if _phase_rank(reached) >= _phase_rank(phase):
                    phase_transition_counts[phase] = phase_transition_counts.get(phase, 0) + 1

    runner = [record for record in closed if _reached_phase(record, "runner")]
    protected = [record for record in closed if _reached_phase(record, "protected")]
    protected_not_runner = [
        record for record in protected if not _reached_phase(record, "runner")
    ]
    runner_summary = _summary_for_records(runner)
    runner_summary["old_exit_reason_mix"] = runner_summary["exit_reason_mix"]
    protected_summary = _summary_for_records(protected)
    protected_summary["protected_not_runner_count"] = len(protected_not_runner)
    protected_summary["protected_not_runner_exit_reason_mix"] = _exit_reason_mix(
        protected_not_runner
    )

    summary: dict[str, Any] = {
        "by_phase_reached": by_phase,
        "phase_transition_counts": phase_transition_counts,
        "exit_layer_breakdown": _exit_layer_mix(closed),
        "active_stop_source_breakdown": {},
        "runner_capture_summary": runner_summary,
        "protected_trade_summary": protected_summary,
    }
    if managed_mode:
        from research.strategies.ema_pullback.execution.results import (
            build_managed_layer_breakdowns,
        )

        summary.update(build_managed_layer_breakdowns(trade_records))
    return summary
