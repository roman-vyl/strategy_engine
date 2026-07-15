"""Slice 3: stop_management component evaluators."""

from __future__ import annotations

import pandas as pd
import pytest

from research.strategies.ema_pullback.execution.managed_components.snapshot import (
    evaluate_management_layers,
)
from research.strategies.ema_pullback.execution.managed_components.stop import (
    apply_tighten_only_stop,
    evaluate_break_even_stop,
    evaluate_lock_profit_stop,
    evaluate_stop_management,
    merge_stop_candidates,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ManagedExitContext,
    TradeRuntimeState,
    empty_active_management_snapshot,
    run_managed_exit_runtime,
)
from tests.phase_rule_test_helpers import make_phase_rule
from research.strategies.ema_pullback.spec import (
    BreakEvenStopParamsSpec,
    LockProfitStopParamsSpec,
    ManagementActivateWhenSpec,
    StopManagementRuleSpec,
)


def _context(
    *,
    side: str = "long",
    phase: str = "protected",
    entry_price: float = 100.0,
    bar_index: int = 5,
) -> ManagedExitContext:
    return ManagedExitContext(
        bar_index=bar_index,
        time_ms=bar_index,
        open=entry_price,
        high=entry_price + 1,
        low=entry_price - 1,
        close=entry_price + 0.5,
        side=side,  # type: ignore[arg-type]
        entry_price=entry_price,
        phase=phase,  # type: ignore[arg-type]
        mfe_pct=0.02,
        mae_pct=0.01,
        bars_in_trade=bar_index + 1,
    )


def _atr_series(value: float, *, length: int = 10) -> dict[tuple[str, int], pd.Series]:
    return {("base", 14): pd.Series([value] * length, dtype=float)}


def _be_rule(
    *,
    phase_at_least: str = "protected",
    buffer: float = 0.0,
    rule_id: str = "be",
) -> StopManagementRuleSpec:
    return StopManagementRuleSpec(
        rule_id=rule_id,
        component_id="break_even_stop",
        activate_when=ManagementActivateWhenSpec(phase_at_least=phase_at_least),  # type: ignore[arg-type]
        params=BreakEvenStopParamsSpec(buffer_type="none", buffer=buffer),
    )


def _lock_rule(
    *,
    phase_at_least: str = "protected",
    lock_atr: float = 0.5,
    rule_id: str = "lock",
) -> StopManagementRuleSpec:
    return StopManagementRuleSpec(
        rule_id=rule_id,
        component_id="lock_profit_stop",
        activate_when=ManagementActivateWhenSpec(phase_at_least=phase_at_least),  # type: ignore[arg-type]
        params=LockProfitStopParamsSpec(lock_atr=lock_atr, atr_period=14),
    )


def _runtime_state(trade_id: str = "T1", side: str = "long") -> TradeRuntimeState:
    return TradeRuntimeState(
        trade_id=trade_id,
        side=side,  # type: ignore[arg-type]
        entry_idx=0,
        entry_time_ms=0,
        entry_price=100.0,
        bars_in_trade=6,
        phase="protected",
        max_phase_reached="protected",
        best_price=102.0,
        worst_price=99.0,
        mfe_price=102.0,
        mfe_pct=0.02,
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


def test_break_even_stop_inactive_before_protected() -> None:
    rule = _be_rule()
    price = evaluate_break_even_stop(
        rule,
        context=_context(phase="proven"),
        atr_series_by_key={},
    )
    assert price is None


def test_break_even_stop_long_side_aware_buffer() -> None:
    rule = _be_rule(buffer=0.25)
    price = evaluate_break_even_stop(
        rule,
        context=_context(side="long", entry_price=100.0),
        atr_series_by_key={},
    )
    assert price == pytest.approx(100.25)


def test_break_even_stop_short_side_aware_buffer() -> None:
    rule = _be_rule(buffer=0.25)
    price = evaluate_break_even_stop(
        rule,
        context=_context(side="short", entry_price=100.0),
        atr_series_by_key={},
    )
    assert price == pytest.approx(99.75)


def test_break_even_after_protected_emits_active_stop_updated() -> None:
    high = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    low = _series([99.0, 98.0, 99.0, 100.0, 101.0, 102.0])
    close = _series([100.0, 100.5, 101.5, 102.5, 103.5, 104.5])
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
                "exit_price": 104.5,
                "exit_reason": "signal:exit",
            }
        ],
        open_=open_,
        high=high,
        low=low,
        close=close,
        phase_rules=(
            make_phase_rule(
                "to_protected",
                "protected",
                "bars_in_trade",
                {"threshold": 2},
            ),
        ),
        stop_management=(_be_rule(buffer=0.0),),
    )

    stop_events = [
        event for event in result.events if event.event_type == "active_stop_updated"
    ]
    assert len(stop_events) == 1
    assert stop_events[0].component_id == "break_even_stop"
    assert stop_events[0].stop_price == pytest.approx(100.0)
    assert result.states_by_trade_id["L1"].active_management.active_stop_price == pytest.approx(
        100.0
    )
    assert any(
        candidate.component_id == "break_even_stop"
        for candidate in result.states_by_trade_id["L1"].exit_candidates
    )


def test_lock_profit_stop_long_formula() -> None:
    rule = _lock_rule(lock_atr=0.5)
    price = evaluate_lock_profit_stop(
        rule,
        context=_context(side="long", entry_price=100.0),
        atr_series_by_key=_atr_series(2.0),
    )
    assert price == pytest.approx(101.0)


def test_lock_profit_stop_short_formula() -> None:
    rule = _lock_rule(lock_atr=0.5)
    price = evaluate_lock_profit_stop(
        rule,
        context=_context(side="short", entry_price=100.0),
        atr_series_by_key=_atr_series(2.0),
    )
    assert price == pytest.approx(99.0)


def test_lock_profit_stop_tighten_only_long_no_update_event() -> None:
    from research.strategies.ema_pullback.execution.trade_runtime import ActiveManagementSnapshot

    previous = ActiveManagementSnapshot(
        active_stop_price=101.0,
        active_stop_rule_id="lock",
        active_stop_component_id="lock_profit_stop",
    )
    tightened = apply_tighten_only_stop(101.0, 100.5, side="long")
    assert tightened == pytest.approx(101.0)

    result = evaluate_management_layers(
        _runtime_state(),
        context=_context(side="long"),
        stop_management=(_lock_rule(lock_atr=0.25),),
        take_management=(),
        runtime_exits=(),
        previous=previous,
        atr_series_by_key=_atr_series(2.0),
    )
    stop_events = [
        event for event in result.events if event.event_type == "active_stop_updated"
    ]
    assert stop_events == []
    assert result.snapshot.active_stop_price == pytest.approx(101.0)


def test_lock_profit_stop_tighten_only_short_no_update_event() -> None:
    from research.strategies.ema_pullback.execution.trade_runtime import ActiveManagementSnapshot

    previous = ActiveManagementSnapshot(
        active_stop_price=99.0,
        active_stop_rule_id="lock",
        active_stop_component_id="lock_profit_stop",
    )
    tightened = apply_tighten_only_stop(99.0, 99.5, side="short")
    assert tightened == pytest.approx(99.0)

    result = evaluate_management_layers(
        _runtime_state(side="short"),
        context=_context(side="short"),
        stop_management=(_lock_rule(lock_atr=0.25),),
        take_management=(),
        runtime_exits=(),
        previous=previous,
        atr_series_by_key=_atr_series(2.0),
    )
    stop_events = [
        event for event in result.events if event.event_type == "active_stop_updated"
    ]
    assert stop_events == []
    assert result.snapshot.active_stop_price == pytest.approx(99.0)


def test_merge_stop_rules_long_be_and_lock() -> None:
    context = _context(side="long", entry_price=100.0)
    atr = _atr_series(2.0)
    candidates = evaluate_stop_management(
        (_be_rule(buffer=0.0, rule_id="be"), _lock_rule(lock_atr=0.5, rule_id="lock")),
        context=context,
        atr_series_by_key=atr,
    )
    merged = merge_stop_candidates(candidates, side="long")
    assert merged is not None
    assert merged.stop_price == pytest.approx(101.0)
    assert merged.rule_id == "lock"


def test_merge_stop_rules_short_be_and_lock() -> None:
    context = _context(side="short", entry_price=100.0)
    atr = _atr_series(2.0)
    candidates = evaluate_stop_management(
        (_be_rule(buffer=0.0, rule_id="be"), _lock_rule(lock_atr=0.5, rule_id="lock")),
        context=context,
        atr_series_by_key=atr,
    )
    merged = merge_stop_candidates(candidates, side="short")
    assert merged is not None
    assert merged.stop_price == pytest.approx(99.0)
    assert merged.rule_id == "lock"


def test_missing_atr_skips_lock_profit_update() -> None:
    rule = _lock_rule()
    price = evaluate_lock_profit_stop(
        rule,
        context=_context(),
        atr_series_by_key={},
    )
    assert price is None

    result = evaluate_management_layers(
        _runtime_state(),
        context=_context(),
        stop_management=(rule,),
        take_management=(),
        runtime_exits=(),
        previous=empty_active_management_snapshot(),
        atr_series_by_key={},
    )
    assert result.events == []
    assert result.snapshot.active_stop_price is None


def test_non_finite_atr_skips_update() -> None:
    rule = _lock_rule()
    atr = {("base", 14): pd.Series([float("nan")] * 5, dtype=float)}
    price = evaluate_lock_profit_stop(
        rule,
        context=_context(bar_index=0),
        atr_series_by_key=atr,
    )
    assert price is None


def test_merge_stop_candidates_empty() -> None:
    assert merge_stop_candidates([], side="long") is None
