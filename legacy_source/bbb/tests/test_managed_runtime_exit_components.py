"""Slice 3: runtime_exits component evaluators."""

from __future__ import annotations

import pandas as pd
import pytest

from research.strategies.ema_pullback.execution.managed_components.runtime_exit import (
    evaluate_runtime_exits,
)
from research.strategies.ema_pullback.execution.managed_components.snapshot import (
    evaluate_management_layers,
)
from research.strategies.ema_pullback.execution.trade_runtime import (
    ManagedExitContext,
    TradeRuntimeState,
    empty_active_management_snapshot,
    run_managed_exit_runtime,
)
from tests.phase_rule_test_helpers import make_phase_rule
from research.strategies.ema_pullback.spec import (
    ManagementActivateWhenSpec,
    PhaseRuntimeExitParamsSpec,
    RuntimeExitRuleSpec,
)


def _context(*, phase: str = "exhaustion", close: float = 97.5) -> ManagedExitContext:
    return ManagedExitContext(
        bar_index=12,
        time_ms=12,
        open=98.0,
        high=99.0,
        low=96.0,
        close=close,
        side="long",
        entry_price=100.0,
        phase=phase,  # type: ignore[arg-type]
        mfe_pct=0.03,
        mae_pct=0.02,
        bars_in_trade=13,
    )


def _runtime_exit_rule(*, phase_at_least: str = "exhaustion") -> RuntimeExitRuleSpec:
    return RuntimeExitRuleSpec(
        rule_id="exit_on_exhaustion",
        component_id="phase_runtime_exit",
        role="exit_management.runtime_exit",
        activate_when=ManagementActivateWhenSpec(phase_at_least=phase_at_least),  # type: ignore[arg-type]
        exit_kind="market_close",
        params=PhaseRuntimeExitParamsSpec(exit_price="close"),
    )


def _runtime_state() -> TradeRuntimeState:
    return TradeRuntimeState(
        trade_id="T1",
        side="long",
        entry_idx=0,
        entry_time_ms=0,
        entry_price=100.0,
        bars_in_trade=13,
        phase="exhaustion",
        max_phase_reached="exhaustion",
        best_price=103.0,
        worst_price=96.0,
        mfe_price=103.0,
        mfe_pct=0.03,
        mae_price=96.0,
        mae_pct=0.04,
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


def test_phase_runtime_exit_inactive_before_threshold() -> None:
    rule = _runtime_exit_rule(phase_at_least="exhaustion")
    triggers = evaluate_runtime_exits((rule,), context=_context(phase="runner"))
    assert triggers == []


def test_phase_runtime_exit_active_at_exhaustion() -> None:
    rule = _runtime_exit_rule()
    close_price = 97.5
    triggers = evaluate_runtime_exits(
        (rule,),
        context=_context(phase="exhaustion", close=close_price),
    )
    assert len(triggers) == 1
    assert triggers[0].exit_price == pytest.approx(close_price)


def test_runtime_exit_candidate_price_is_bar_close() -> None:
    rule = _runtime_exit_rule()
    close_price = 96.25
    result = evaluate_management_layers(
        _runtime_state(),
        context=_context(phase="exhaustion", close=close_price),
        stop_management=(),
        take_management=(),
        runtime_exits=(rule,),
        previous=empty_active_management_snapshot(),
        atr_series_by_key={},
    )
    runtime_events = [
        event for event in result.events if event.event_type == "runtime_exit_triggered"
    ]
    assert len(runtime_events) == 1
    assert runtime_events[0].price == pytest.approx(close_price)
    assert len(result.candidates) == 1
    assert result.candidates[0].price == pytest.approx(close_price)
    assert result.candidates[0].reason == "runtime_exit:market_close"


def test_no_managed_close_or_exit_rule_triggered_in_slice_3() -> None:
    high = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    low = _series([99.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0])
    close = _series([100.0, 100.5, 101.5, 102.5, 103.5, 104.5, 105.0])
    open_ = close - 0.1

    result = run_managed_exit_runtime(
        trade_records=[
            {
                "trade_id": "L1",
                "status": "closed",
                "direction": "long",
                "entry_idx": 0,
                "exit_idx": 6,
                "entry_price": 100.0,
                "exit_price": 105.0,
                "exit_reason": "signal:exit",
            }
        ],
        open_=open_,
        high=high,
        low=low,
        close=close,
        phase_rules=(
            make_phase_rule(
                "to_exhaustion",
                "exhaustion",
                "bars_in_trade",
                {"threshold": 5},
            ),
        ),
        runtime_exits=(_runtime_exit_rule(),),
    )

    assert not any(event.event_type == "exit_rule_triggered" for event in result.events)
    exit_executed = [event for event in result.events if event.event_type == "exit_executed"]
    assert len(exit_executed) == 1
    assert exit_executed[0].metadata.get("exit_reason") == "signal:exit"
