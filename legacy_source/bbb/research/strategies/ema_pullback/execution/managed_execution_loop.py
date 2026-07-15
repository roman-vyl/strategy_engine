"""Execution-layer integration loop with managed exit provider (Slice 4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from research.strategies.ema_pullback.execution.exit_arbitration import (
    ExitArbitrator,
    arbitration_metadata,
)
from research.strategies.ema_pullback.execution.exit_attribution import ExitAttributionResult
from research.strategies.ema_pullback.execution.exit_policy_candidates import (
    collect_exit_policy_bar_candidates,
    profile_at_bar,
)
from research.strategies.ema_pullback.execution.exits import PortfolioExitOutputs
from research.strategies.ema_pullback.execution.managed_exit_provider import ManagedExitProvider
from research.strategies.ema_pullback.consumer_roles import (
    EXIT_LAYER_EXIT_POLICY,
    EXIT_LAYER_RUNTIME_EXIT,
    EXIT_LAYER_STOP_RULE,
    EXIT_OWNER_EXIT_MANAGEMENT,
    EXIT_OWNER_EXIT_POLICY,
    ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ActiveManagementSnapshot,
    ExitCandidate,
    ManagedTradeRuntimeResult,
    ManagedTradeRuntimeState,
    TradeManagementEvent,
    TradeRuntimeState,
    _index_to_time_ms,
    _initial_state,
    empty_active_management_snapshot,
)
from research.strategies.ema_pullback.spec import EmaPullbackStrategySpec


@dataclass
class _OpenPosition:
    trade_id: str
    direction: Literal["long", "short"]
    entry_idx: int
    entry_price: float
    locked_profile: str
    runtime: TradeRuntimeState
    inherited_snapshot: ActiveManagementSnapshot


@dataclass
class ManagedExecutionLoopResult:
    closed: list[dict[str, Any]]
    events: list[TradeManagementEvent]
    states_by_trade_id: dict[str, ManagedTradeRuntimeState]


def _trade_id(direction: str, entry_idx: int) -> str:
    return f"{direction}:{entry_idx}"


def _exit_attribution_from_candidate(winner: ExitCandidate) -> ExitAttributionResult:
    if winner.layer == "exit_management":
        prefix = winner.reason.split(":", 1)[0]
        if prefix == "active_stop":
            kind = winner.component_id or "managed_stop"
            return ExitAttributionResult(
                f"exit_management:{winner.rule_id}",
                "exit_management",
                None,
                winner.component_id,
                winner.rule_id,
                kind,
            )
        return ExitAttributionResult(
            f"exit_management:{winner.rule_id}",
            "exit_management",
            None,
            winner.component_id,
            winner.rule_id,
            "runtime_exit",
        )
    reason = winner.reason
    return ExitAttributionResult(
        reason,
        "always_on" if winner.layer == "exit_policy" else None,
        None,
        winner.component_id,
        winner.rule_id,
        winner.candidate_type,
    )


def _precise_exit_layer(winner: ExitCandidate) -> str:
    if winner.attribution_layer:
        return winner.attribution_layer
    if winner.layer == "exit_policy":
        return EXIT_LAYER_EXIT_POLICY
    if winner.reason.startswith("active_stop:"):
        return EXIT_LAYER_STOP_RULE
    if winner.reason.startswith("runtime_exit:"):
        return EXIT_LAYER_RUNTIME_EXIT
    return winner.layer


def _exit_owner_for_layer(exit_layer: str) -> str:
    if exit_layer == EXIT_LAYER_EXIT_POLICY:
        return EXIT_OWNER_EXIT_POLICY
    return EXIT_OWNER_EXIT_MANAGEMENT


def _close_events(
    pos: _OpenPosition,
    *,
    bar_idx: int,
    time_ms: int,
    winner: ExitCandidate,
    arbitration: object,
) -> list[TradeManagementEvent]:
    meta = arbitration_metadata(arbitration)  # type: ignore[arg-type]
    exit_layer = _precise_exit_layer(winner)
    exit_owner = winner.exit_owner or _exit_owner_for_layer(exit_layer)
    role = winner.role
    if role is None and exit_layer == EXIT_LAYER_RUNTIME_EXIT:
        role = ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT
    close_meta = {
        "exit_layer": exit_layer,
        "exit_owner": exit_owner,
        "exit_kind": winner.exit_kind,
        "role": role,
        **meta,
    }
    return [
        TradeManagementEvent(
            trade_id=pos.trade_id,
            time_ms=time_ms,
            bar_index=bar_idx,
            side=pos.direction,
            event_type="exit_rule_triggered",
            from_phase=pos.runtime.phase,
            to_phase=None,
            rule_id=winner.rule_id,
            component_id=winner.component_id,
            price=winner.price,
            stop_price=pos.inherited_snapshot.active_stop_price,
            mfe_pct=pos.runtime.mfe_pct,
            mae_pct=pos.runtime.mae_pct,
            bars_in_trade=pos.runtime.bars_in_trade,
            metadata=close_meta,
        ),
        TradeManagementEvent(
            trade_id=pos.trade_id,
            time_ms=time_ms,
            bar_index=bar_idx,
            side=pos.direction,
            event_type="exit_executed",
            from_phase=pos.runtime.phase,
            to_phase=None,
            rule_id=winner.rule_id,
            component_id=winner.component_id,
            price=winner.price,
            stop_price=pos.inherited_snapshot.active_stop_price,
            mfe_pct=pos.runtime.mfe_pct,
            mae_pct=pos.runtime.mae_pct,
            bars_in_trade=pos.runtime.bars_in_trade,
            metadata={
                **close_meta,
                "exit_reason": (
                    f"exit_management:{winner.rule_id}"
                    if winner.layer == "exit_management"
                    else winner.reason
                ),
            },
        ),
    ]


def run_managed_execution_loop(
    *,
    spec: EmaPullbackStrategySpec,
    close: pd.Series,
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    entries: pd.Series,
    short_entries: pd.Series,
    exit_outputs: PortfolioExitOutputs,
    provider: ManagedExitProvider,
    component_map: dict[str, str] | None = None,
) -> ManagedExecutionLoopResult:
    index = close.index
    n = len(close)
    arbitrator = ExitArbitrator()
    open_pos: _OpenPosition | None = None
    closed: list[dict[str, Any]] = []
    events: list[TradeManagementEvent] = []
    states_by_trade_id: dict[str, ManagedTradeRuntimeState] = {}
    for bar_idx in range(n):
        o = float(open_.iloc[bar_idx])
        h = float(high.iloc[bar_idx])
        l = float(low.iloc[bar_idx])
        c = float(close.iloc[bar_idx])
        time_ms = _index_to_time_ms(index, bar_idx)
        position_was_open_at_bar_start = open_pos is not None
        opened_on_this_bar = False

        if open_pos is not None:
            inherited = open_pos.inherited_snapshot
            policy_candidates = collect_exit_policy_bar_candidates(
                bar_idx=bar_idx,
                direction=open_pos.direction,
                entry_idx=open_pos.entry_idx,
                entry_price=open_pos.entry_price,
                locked_profile=open_pos.locked_profile,
                open_=o,
                high=h,
                low=l,
                close=c,
                exit_outputs=exit_outputs,
                inherited_take_profile=inherited.active_take_profile,
                component_map=component_map,
            )
            managed_candidates = provider.get_bar_open_candidates(
                inherited,
                bar_idx=bar_idx,
                direction=open_pos.direction,
                open_=o,
                high=h,
                low=l,
                close=c,
            )
            arbitration = arbitrator.select_winner(
                [*policy_candidates, *managed_candidates],
                bar_index=bar_idx,
            )
            if arbitration.winner is not None:
                winner = arbitration.winner
                events.extend(
                    _close_events(
                        open_pos,
                        bar_idx=bar_idx,
                        time_ms=time_ms,
                        winner=winner,
                        arbitration=arbitration,
                    )
                )
                exit_attr = _exit_attribution_from_candidate(winner)
                precise_layer = _precise_exit_layer(winner)
                closed.append(
                    {
                        "trade_id": open_pos.trade_id,
                        "direction": open_pos.direction,
                        "entry_idx": open_pos.entry_idx,
                        "entry_price": open_pos.entry_price,
                        "exit_idx": bar_idx,
                        "exit_price": winner.price,
                        "locked_profile": open_pos.locked_profile,
                        "exit_attribution": exit_attr,
                        "exit_layer": precise_layer,
                        "exit_owner": winner.exit_owner
                        or _exit_owner_for_layer(precise_layer),
                        "winner": winner,
                    }
                )
                states_by_trade_id[open_pos.trade_id] = ManagedTradeRuntimeState(
                    runtime=open_pos.runtime,
                    active_management=inherited,
                )
                open_pos = None

        if not position_was_open_at_bar_start:
            if open_pos is None and bool(entries.iloc[bar_idx]) and spec.trade_sides.includes("long"):
                prof = profile_at_bar(exit_outputs, bar_idx, "long")
                runtime = _initial_state(
                    {
                        "trade_id": _trade_id("long", bar_idx),
                        "direction": "long",
                        "entry_price": c,
                        "entry_profile": prof,
                    },
                    entry_idx=bar_idx,
                    index=index,
                )
                assert runtime is not None
                open_pos = _OpenPosition(
                    trade_id=runtime.trade_id,
                    direction="long",
                    entry_idx=bar_idx,
                    entry_price=c,
                    locked_profile=prof,
                    runtime=runtime,
                    inherited_snapshot=empty_active_management_snapshot(),
                )
                opened_on_this_bar = True
            elif open_pos is None and bool(short_entries.iloc[bar_idx]) and spec.trade_sides.includes("short"):
                prof = profile_at_bar(exit_outputs, bar_idx, "short")
                runtime = _initial_state(
                    {
                        "trade_id": _trade_id("short", bar_idx),
                        "direction": "short",
                        "entry_price": c,
                        "entry_profile": prof,
                    },
                    entry_idx=bar_idx,
                    index=index,
                )
                assert runtime is not None
                open_pos = _OpenPosition(
                    trade_id=runtime.trade_id,
                    direction="short",
                    entry_idx=bar_idx,
                    entry_price=c,
                    locked_profile=prof,
                    runtime=runtime,
                    inherited_snapshot=empty_active_management_snapshot(),
                )
                opened_on_this_bar = True

        if open_pos is not None and not opened_on_this_bar:
            update = provider.update_end_of_bar_snapshot(
                open_pos.runtime,
                inherited=open_pos.inherited_snapshot,
                bar_idx=bar_idx,
                time_ms=time_ms,
                open_=o,
                high=h,
                low=l,
                close=c,
            )
            events.extend(update.events)
            open_pos.runtime = update.runtime
            open_pos.inherited_snapshot = update.snapshot

    if open_pos is not None:
        closed.append(
            {
                "trade_id": open_pos.trade_id,
                "direction": open_pos.direction,
                "entry_idx": open_pos.entry_idx,
                "entry_price": open_pos.entry_price,
                "exit_idx": n - 1,
                "exit_price": float(close.iloc[n - 1]),
                "locked_profile": open_pos.locked_profile,
                "open": True,
            }
        )
        states_by_trade_id[open_pos.trade_id] = ManagedTradeRuntimeState(
            runtime=open_pos.runtime,
            active_management=open_pos.inherited_snapshot,
        )

    return ManagedExecutionLoopResult(closed=closed, events=events, states_by_trade_id=states_by_trade_id)


def execution_result_to_managed_runtime_result(
    result: ManagedExecutionLoopResult,
) -> ManagedTradeRuntimeResult:
    return ManagedTradeRuntimeResult(
        states_by_trade_id=result.states_by_trade_id,
        events=result.events,
    )
