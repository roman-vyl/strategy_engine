"""Slice 3: take_management component evaluators."""

from __future__ import annotations

import pandas as pd
import pytest

from research.strategies.ema_pullback.execution.managed_components.snapshot import (
    evaluate_management_layers,
)
from research.strategies.ema_pullback.execution.managed_components.take import (
    ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP,
    evaluate_take_management,
    normalize_take_profile_action,
    take_profile_descriptor,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ACTIVE_TAKE_PROFILE_INITIAL,
    ManagedExitContext,
    TradeRuntimeState,
    empty_active_management_snapshot,
    run_managed_exit_runtime,
)
from tests.phase_rule_test_helpers import make_phase_rule
from research.strategies.ema_pullback.spec import (
    ManagementActivateWhenSpec,
    TakeManagementRuleSpec,
    TakeProfileSwitchParamsSpec,
)


def _context(*, phase: str = "runner", side: str = "long") -> ManagedExitContext:
    return ManagedExitContext(
        bar_index=10,
        time_ms=10,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        side=side,  # type: ignore[arg-type]
        entry_price=100.0,
        phase=phase,  # type: ignore[arg-type]
        mfe_pct=0.05,
        mae_pct=0.01,
        bars_in_trade=11,
    )


def _take_rule(
    action: str,
    *,
    phase_at_least: str = "runner",
    rule_id: str = "take_switch",
) -> TakeManagementRuleSpec:
    return TakeManagementRuleSpec(
        rule_id=rule_id,
        component_id="take_profile_switch",
        activate_when=ManagementActivateWhenSpec(phase_at_least=phase_at_least),  # type: ignore[arg-type]
        params=TakeProfileSwitchParamsSpec(
            action=normalize_take_profile_action(action),  # type: ignore[arg-type]
        ),
    )


def _runtime_state() -> TradeRuntimeState:
    return TradeRuntimeState(
        trade_id="T1",
        side="long",
        entry_idx=0,
        entry_time_ms=0,
        entry_price=100.0,
        bars_in_trade=11,
        phase="runner",
        max_phase_reached="runner",
        best_price=105.0,
        worst_price=99.0,
        mfe_price=105.0,
        mfe_pct=0.05,
        mae_price=99.0,
        mae_pct=0.01,
        active_stop_price=None,
        active_stop_source=None,
        initial_stop_price=None,
        initial_take_profit_price=None,
        locked_exit_profile=None,
    )


def _series(values: list[float]) -> pd.Series:
    return pd.Series(
        values,
        index=pd.date_range("2024-01-01", periods=len(values), freq="h", tz="UTC"),
        dtype=float,
    )


def test_keep_initial_does_not_emit_fake_profile_change() -> None:
    rule = _take_rule("keep_initial")
    selection = evaluate_take_management((rule,), context=_context())
    assert selection is not None
    assert selection.profile == ACTIVE_TAKE_PROFILE_INITIAL

    result = evaluate_management_layers(
        _runtime_state(),
        context=_context(),
        stop_management=(),
        take_management=(rule,),
        runtime_exits=(),
        previous=empty_active_management_snapshot(),
        atr_series_by_key={},
    )
    take_events = [
        event for event in result.events if event.event_type == "active_take_updated"
    ]
    assert take_events == []
    assert result.snapshot.active_take_profile == ACTIVE_TAKE_PROFILE_INITIAL


def test_disable_initial_tp_emits_active_take_updated() -> None:
    rule = _take_rule("disable_initial_tp")
    result = evaluate_management_layers(
        _runtime_state(),
        context=_context(phase="runner"),
        stop_management=(),
        take_management=(rule,),
        runtime_exits=(),
        previous=empty_active_management_snapshot(),
        atr_series_by_key={},
    )
    take_events = [
        event for event in result.events if event.event_type == "active_take_updated"
    ]
    assert len(take_events) == 1
    assert take_events[0].component_id == "take_profile_switch"
    assert take_events[0].metadata.get("effective_from_bar") == 11
    assert result.snapshot.active_take_profile == ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP


def test_disable_fixed_tp_alias_normalizes_to_disable_initial_tp() -> None:
    rule = _take_rule("disable_fixed_tp")
    result = evaluate_management_layers(
        _runtime_state(),
        context=_context(phase="runner"),
        stop_management=(),
        take_management=(rule,),
        runtime_exits=(),
        previous=empty_active_management_snapshot(),
        atr_series_by_key={},
    )
    assert result.snapshot.active_take_profile == ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP


def test_take_rule_inactive_before_phase_threshold() -> None:
    rule = _take_rule("disable_initial_tp", phase_at_least="runner")
    selection = evaluate_take_management((rule,), context=_context(phase="protected"))
    assert selection is None


def test_take_profile_switch_does_not_mutate_exit_policy_spec() -> None:
    from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec

    spec = make_ema_pullback_strategy_spec()
    exit_policy_before = spec.trade_management.exit_policy
    rule = _take_rule("disable_initial_tp")
    evaluate_management_layers(
        _runtime_state(),
        context=_context(),
        stop_management=(),
        take_management=(rule,),
        runtime_exits=(),
        previous=empty_active_management_snapshot(),
        atr_series_by_key={},
    )
    spec_after = make_ema_pullback_strategy_spec()
    assert spec_after.trade_management.exit_policy == exit_policy_before


def test_disable_initial_tp_via_managed_runtime_replay() -> None:
    high = _series([100.0, 102.0, 104.0, 106.0, 108.0, 110.0])
    low = _series([99.0, 100.0, 102.0, 104.0, 106.0, 108.0])
    close = _series([100.0, 101.0, 103.0, 105.0, 107.0, 109.0])
    open_ = close - 0.1

    result = run_managed_exit_runtime(
        trade_records=[
            {
                "trade_id": "L1",
                "status": "closed",
                "direction": "long",
                "entry_idx": 0,
                "exit_idx": 5,
                "entry_price": 100.0,
                "exit_price": 109.0,
                "exit_reason": "take_profit:tp",
            }
        ],
        open_=open_,
        high=high,
        low=low,
        close=close,
        phase_rules=(
            make_phase_rule(
                "to_runner",
                "runner",
                "bars_in_trade",
                {"threshold": 3},
            ),
        ),
        take_management=(_take_rule("disable_initial_tp"),),
    )

    take_events = [
        event for event in result.events if event.event_type == "active_take_updated"
    ]
    assert len(take_events) >= 1
    assert result.states_by_trade_id["L1"].active_management.active_take_profile == (
        ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP
    )


def test_take_profile_descriptor_mapping() -> None:
    assert take_profile_descriptor("keep_initial") == ACTIVE_TAKE_PROFILE_INITIAL
    assert take_profile_descriptor("disable_initial_tp") == ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP
    assert (
        take_profile_descriptor("disable_fixed_tp")
        == ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP
    )
