"""Runtime reusable signal exits (RSI / EMA cross) phase-gated behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from research.strategies.ema_pullback.execution.managed_components.runtime_exit import (
    compile_runtime_exit_signal_series,
    evaluate_runtime_exits,
)
from research.strategies.ema_pullback.execution.trade_runtime import ManagedExitContext
from research.strategies.ema_pullback.spec import (
    EmaCrossRuntimeExitParamsSpec,
    EmaSpec,
    ManagementActivateWhenSpec,
    RsiFeatureSpec,
    RsiRuntimeExitParamsSpec,
    RuntimeExitRuleSpec,
)
def _context(*, phase: str, bar_index: int = 5, close: float = 100.0) -> ManagedExitContext:
    return ManagedExitContext(
        bar_index=bar_index,
        time_ms=bar_index,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        side="long",
        entry_price=99.0,
        phase=phase,  # type: ignore[arg-type]
        mfe_pct=0.02,
        mae_pct=0.01,
        bars_in_trade=6,
    )


def _rsi_rule(*, phase_at_least: str = "runner") -> RuntimeExitRuleSpec:
    return RuntimeExitRuleSpec(
        rule_id="runner_rsi",
        component_id="rsi_signal_exit",
        role="exit_management.runtime_exit",
        activate_when=ManagementActivateWhenSpec(phase_at_least=phase_at_least),  # type: ignore[arg-type]
        exit_kind="take_profit",
        params=RsiRuntimeExitParamsSpec(
            rsi=RsiFeatureSpec(timeframe="base", period=14),
            long_exit_above=90.0,
            short_exit_below=10.0,
        ),
    )


def _ema_rule(*, phase_at_least: str = "runner") -> RuntimeExitRuleSpec:
    return RuntimeExitRuleSpec(
        rule_id="runner_ema",
        component_id="ema_cross_loss_exit",
        role="exit_management.runtime_exit",
        activate_when=ManagementActivateWhenSpec(phase_at_least=phase_at_least),  # type: ignore[arg-type]
        exit_kind="protective_exit",
        params=EmaCrossRuntimeExitParamsSpec(
            fast_ema=EmaSpec(source="close", timeframe="base", period=10),
            slow_ema=EmaSpec(source="close", timeframe="base", period=20),
            confirm_bars=1,
        ),
    )


def _df_with_rsi(rsi_values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(rsi_values), freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * len(rsi_values),
            "high": [101.0] * len(rsi_values),
            "low": [99.0] * len(rsi_values),
            "close": [100.0] * len(rsi_values),
            "rsi_base_14": rsi_values,
        },
        index=index,
    )


def test_runtime_rsi_inactive_before_runner() -> None:
    rule = _rsi_rule()
    rsi = pd.Series([95.0] * 6)
    triggers = evaluate_runtime_exits(
        (rule,),
        context=_context(phase="protected", bar_index=5),
        signal_series_by_rule_id={"runner_rsi": rsi},
    )
    assert triggers == []


def test_runtime_rsi_triggers_after_runner_long() -> None:
    rule = _rsi_rule()
    rsi = pd.Series([80.0, 85.0, 88.0, 91.0, 92.0, 93.0])
    triggers = evaluate_runtime_exits(
        (rule,),
        context=_context(phase="runner", bar_index=5, close=101.5),
        signal_series_by_rule_id={"runner_rsi": rsi},
    )
    assert len(triggers) == 1
    assert triggers[0].exit_kind == "take_profit"
    assert triggers[0].exit_price == pytest.approx(101.5)


def test_runtime_rsi_triggers_after_runner_short() -> None:
    rule = _rsi_rule()
    rsi = pd.Series([12.0, 11.0, 10.0, 9.0, 8.0, 7.0])
    context = ManagedExitContext(
        bar_index=5,
        time_ms=5,
        open=100.0,
        high=101.0,
        low=99.0,
        close=98.5,
        side="short",
        entry_price=101.0,
        phase="runner",
        mfe_pct=0.02,
        mae_pct=0.01,
        bars_in_trade=6,
    )
    triggers = evaluate_runtime_exits(
        (rule,),
        context=context,
        signal_series_by_rule_id={"runner_rsi": rsi},
    )
    assert len(triggers) == 1
    assert triggers[0].exit_price == pytest.approx(98.5)


def test_compile_runtime_exit_signal_series_long_rsi() -> None:
    from research.strategies.ema_pullback.features.plan import FeaturePlan

    df = _df_with_rsi([70.0, 75.0, 80.0, 85.0, 92.0, 95.0])
    plan = FeaturePlan(
        features=(),
        anchor_columns={"fast": "e1", "anchor": "e2", "slow": "e3"},
        rsi_columns={("base", 14): "rsi_base_14"},
        ema_columns={},
        adx_dmi_columns={},
        exit_distance_columns={},
        setup_columns_by_instance_id={},
        htf_context_columns_by_ref={},
    )
    rule = _rsi_rule()
    series = compile_runtime_exit_signal_series(rule, df=df, plan=plan, side="long")
    assert series is not None
    assert bool(series.iloc[-1]) is True
