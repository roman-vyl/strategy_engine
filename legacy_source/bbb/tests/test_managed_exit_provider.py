"""Slice 4: managed exit provider unit tests."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from research.strategies.ema_pullback.execution.managed_bar_open_candidates import (
    collect_managed_bar_open_candidates,
)
from research.strategies.ema_pullback.execution.managed_components.take import (
    ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP,
)
from research.strategies.ema_pullback.execution.managed_exit_provider import ManagedExitProvider
from research.strategies.ema_pullback.execution.trade_runtime import (
    ActiveManagementSnapshot,
    TradeRuntimeState,
    empty_active_management_snapshot,
)
from research.strategies.ema_pullback.spec import (
    BreakEvenStopParamsSpec,
    ManagementActivateWhenSpec,
    StopManagementRuleSpec,
)
from tests.phase_rule_test_helpers import make_phase_rule


def _runtime_state(*, phase: str = "initial_risk") -> TradeRuntimeState:
    return TradeRuntimeState(
        trade_id="long:0",
        side="long",
        entry_idx=0,
        entry_time_ms=0,
        entry_price=100.0,
        bars_in_trade=1,
        phase=phase,  # type: ignore[arg-type]
        max_phase_reached=phase,
        best_price=100.0,
        worst_price=100.0,
        mfe_price=100.0,
        mfe_pct=0.0,
        mae_price=100.0,
        mae_pct=0.0,
        active_stop_price=None,
        active_stop_source=None,
        initial_stop_price=None,
        initial_take_profit_price=None,
        locked_exit_profile=None,
    )


def test_inherited_active_stop_returns_managed_stop_candidate() -> None:
    inherited = ActiveManagementSnapshot(
        active_stop_price=100.0,
        active_stop_rule_id="be",
        active_stop_component_id="break_even_stop",
    )
    candidates = collect_managed_bar_open_candidates(
        inherited,
        bar_idx=2,
        direction="long",
        open_=101.0,
        high=101.5,
        low=99.0,
        close=100.5,
    )
    assert len(candidates) == 1
    assert candidates[0].candidate_type == "managed_stop"
    assert candidates[0].layer == "exit_management"


def test_no_inherited_stop_returns_no_managed_stop_candidate() -> None:
    candidates = collect_managed_bar_open_candidates(
        empty_active_management_snapshot(),
        bar_idx=1,
        direction="long",
        open_=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )
    assert candidates == []


def test_end_of_bar_be_snapshot_effective_from_n_plus_1() -> None:
    provider = ManagedExitProvider(
        phase_rules=(
            make_phase_rule(
                "to_protected",
                "protected",
                "bars_in_trade",
                {"threshold": 1},
            ),
        ),
        stop_management=(
            StopManagementRuleSpec(
                rule_id="be",
                component_id="break_even_stop",
                activate_when=ManagementActivateWhenSpec(phase_at_least="protected"),
                params=BreakEvenStopParamsSpec(buffer_type="none", buffer=0.0),
            ),
        ),
        take_management=(),
        runtime_exits=(),
    )
    runtime = _runtime_state()
    inherited = empty_active_management_snapshot()
    update = provider.update_end_of_bar_snapshot(
        runtime,
        inherited=inherited,
        bar_idx=1,
        time_ms=1,
        open_=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
    )
    stop_events = [e for e in update.events if e.event_type == "active_stop_updated"]
    assert len(stop_events) == 1
    assert stop_events[0].metadata.get("effective_from_bar") == 2
    assert update.snapshot.active_stop_price == 100.0

    bar_open = provider.get_bar_open_candidates(
        inherited,
        bar_idx=1,
        direction="long",
        open_=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
    )
    assert not any(c.candidate_type == "managed_stop" for c in bar_open)


def test_runtime_exit_armed_end_of_bar_n_not_bar_open_on_n() -> None:
    from research.strategies.ema_pullback.spec import (
        PhaseRuntimeExitParamsSpec,
        RuntimeExitRuleSpec,
    )

    provider = ManagedExitProvider(
        phase_rules=(
            make_phase_rule(
                "to_exhaustion",
                "exhaustion",
                "bars_in_trade",
                {"threshold": 1},
            ),
        ),
        stop_management=(),
        take_management=(),
        runtime_exits=(
            RuntimeExitRuleSpec(
                rule_id="exit_ex",
                component_id="phase_runtime_exit",
                role="exit_management.runtime_exit",
                activate_when=ManagementActivateWhenSpec(phase_at_least="exhaustion"),
                exit_kind="market_close",
                params=PhaseRuntimeExitParamsSpec(exit_price="close"),
            ),
        ),
    )
    inherited = empty_active_management_snapshot()
    runtime = _runtime_state()
    update = provider.update_end_of_bar_snapshot(
        runtime,
        inherited=inherited,
        bar_idx=1,
        time_ms=1,
        open_=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )
    assert update.snapshot.active_runtime_exit_rules == ("exit_ex",)
    bar_open_same = provider.get_bar_open_candidates(
        inherited,
        bar_idx=1,
        direction="long",
        open_=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )
    assert bar_open_same == []

    bar_open_next = provider.get_bar_open_candidates(
        update.snapshot,
        bar_idx=2,
        direction="long",
        open_=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )
    assert len(bar_open_next) == 1
    assert bar_open_next[0].candidate_type == "runtime_close"


def test_inherited_disable_initial_tp_profile_state() -> None:
    inherited = ActiveManagementSnapshot(
        active_take_profile=ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP,
        active_take_rule_id="disable_tp",
        active_take_component_id="take_profile_switch",
    )
    assert inherited.active_take_profile == "disable_initial_tp"
