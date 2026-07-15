"""Managed exit provider: bar-open candidates and end-of-bar snapshot updates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from research.strategies.ema_pullback.execution.managed_bar_open_candidates import (
    collect_managed_bar_open_candidates,
)
from research.strategies.ema_pullback.execution.managed_components.snapshot import (
    evaluate_management_layers,
)
from research.strategies.ema_pullback.phase_rule_conditions.registry import (
    PhaseRuleEvaluationContext,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ActiveManagementSnapshot,
    ExitCandidate,
    ManagedExitContext,
    TradeManagementEvent,
    TradeRuntimeState,
    _build_managed_exit_context,
    evaluate_phase_rules,
    update_trade_runtime_state,
)
from research.strategies.ema_pullback.spec import (
    PhaseRuleSpec,
    RuntimeExitRuleSpec,
    StopManagementRuleSpec,
    TakeManagementRuleSpec,
)


@dataclass(frozen=True)
class EndOfBarProviderUpdate:
    runtime: TradeRuntimeState
    snapshot: ActiveManagementSnapshot
    events: tuple[TradeManagementEvent, ...] = ()


@dataclass
class ManagedExitProvider:
    phase_rules: tuple[PhaseRuleSpec, ...]
    stop_management: tuple[StopManagementRuleSpec, ...]
    take_management: tuple[TakeManagementRuleSpec, ...]
    runtime_exits: tuple[RuntimeExitRuleSpec, ...]
    phase_eval_context: PhaseRuleEvaluationContext = field(
        default_factory=lambda: PhaseRuleEvaluationContext(
            atr_series_by_key={},
            adx_dmi_series_by_key={},
        )
    )
    runtime_exit_signals_by_side: dict[str, dict[str, pd.Series]] = field(
        default_factory=dict
    )

    def get_bar_open_candidates(
        self,
        inherited: ActiveManagementSnapshot,
        *,
        bar_idx: int,
        direction: Literal["long", "short"],
        open_: float,
        high: float,
        low: float,
        close: float,
    ) -> list[ExitCandidate]:
        return collect_managed_bar_open_candidates(
            inherited,
            bar_idx=bar_idx,
            direction=direction,
            open_=open_,
            high=high,
            low=low,
            close=close,
            runtime_exits=self.runtime_exits,
        )

    def update_end_of_bar_snapshot(
        self,
        runtime: TradeRuntimeState,
        *,
        inherited: ActiveManagementSnapshot,
        bar_idx: int,
        time_ms: int,
        open_: float,
        high: float,
        low: float,
        close: float,
    ) -> EndOfBarProviderUpdate:
        update_trade_runtime_state(
            runtime,
            bar_index=bar_idx,
            high=high,
            low=low,
        )
        events: list[TradeManagementEvent] = list(
            evaluate_phase_rules(
                runtime,
                self.phase_rules,
                bar_index=bar_idx,
                time_ms=time_ms,
                eval_context=self.phase_eval_context,
            )
        )
        context = _build_managed_exit_context(
            runtime,
            bar_index=bar_idx,
            time_ms=time_ms,
            open_=open_,
            high=high,
            low=low,
            close=close,
        )
        layer_result = evaluate_management_layers(
            runtime,
            context=context,
            stop_management=self.stop_management,
            take_management=self.take_management,
            runtime_exits=self.runtime_exits,
            previous=inherited,
            atr_series_by_key=self.phase_eval_context.atr_series_by_key,
            runtime_exit_signals_by_rule_id=self.runtime_exit_signals_by_side.get(
                context.side, {}
            ),
        )
        events.extend(layer_result.events)
        return EndOfBarProviderUpdate(
            runtime=runtime,
            snapshot=layer_result.snapshot,
            events=tuple(events),
        )
