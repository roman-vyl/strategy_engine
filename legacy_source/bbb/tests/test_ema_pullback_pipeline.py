from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.strategies.ema_pullback.component_builders import (
    exit_atr_stop_loss,
    exit_atr_take_profit,
    exit_rsi,
    trade_management,
)
from tests.ema_pullback_context_helpers import (
    build_exit_outputs_with_context_bundle,
    exit_policy_htf_consumption,
    htf_strategy_contexts,
)
from research.strategies.ema_pullback.execution.exits import (
    build_exit_outputs_from_spec,
    compose_exit_signals,
)
from research.strategies.ema_pullback.execution.signals import (
    build_signals_from_spec,
    compose_blocker_signals,
)
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec


def _ohlcv() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
    close = pd.Series([99.0, 98.0, 101.0, 102.0, 103.0, 104.0, 100.0, 105.0], index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": pd.Series([101.0, 99.0, 100.0, 103.0, 104.0, 105.0, 98.0, 106.0], index=idx),
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )


def test_build_signals_from_spec_uses_component_registry_and_plan_columns() -> None:
    spec = make_ema_pullback_strategy_spec()
    plan = build_feature_plan_from_strategy_spec(spec)
    df = add_feature_columns_from_plan(_ohlcv(), plan)

    # Enforce deterministic component behavior for this unit test.
    df[plan.anchor_columns["fast"]] = [11, 12, 10, 14, 15, 16, 11, 17]
    df[plan.anchor_columns["anchor"]] = [10, 11, 10, 13, 14, 15, 10, 16]
    df[plan.anchor_columns["slow"]] = [9, 10, 9, 12, 13, 14, 9, 15]

    signals = build_signals_from_spec(df, spec, plan)
    assert signals.entries.dtype == bool
    assert signals.short_entries.dtype == bool
    assert len(signals.entries) == len(df)
    assert len(signals.short_entries) == len(df)
    assert bool(signals.short_entries.any()) is False
    assert bool(signals.entries.isna().any()) is False
    assert signals.output_counters[0]["role"] == "blockers"
    assert signals.output_counters[0]["instance_id"] == "no_blockers"
    assert signals.output_counters[0]["counters"] == {
        "allowed_count": len(df),
        "blocked_count": 0,
    }


def test_build_exit_outputs_from_spec_uses_unified_exit_rules() -> None:
    spec = make_ema_pullback_strategy_spec()
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC")
    ohlcv = _ohlcv().reindex(idx).ffill()
    df = add_feature_columns_from_plan(ohlcv, plan)

    df[plan.anchor_columns["anchor"]] = df["close"]
    exit_outputs = build_exit_outputs_from_spec(df, spec, plan)

    assert exit_outputs.exits.dtype == bool
    assert exit_outputs.short_exits.dtype == bool
    assert len(exit_outputs.exits) == len(df)
    assert len(exit_outputs.short_exits) == len(df)
    assert bool(exit_outputs.exits.any()) is False
    assert bool(exit_outputs.short_exits.any()) is False
    assert "stop_loss" in plan.exit_distance_columns
    assert "take_profit" in plan.exit_distance_columns
    assert "atr_stop_loss" in plan.exit_distance_columns
    assert "atr_take_profit" in plan.exit_distance_columns
    assert exit_outputs.sl_stop.notna().any()
    assert exit_outputs.tp_stop.notna().any()
    assert [counter["instance_id"] for counter in exit_outputs.output_counters] == [
        "atr_stop_loss",
        "atr_take_profit",
    ]
    assert all(
        counter["counters"]["ready_count"] == counter["counters"]["non_null_distance_count"]
        for counter in exit_outputs.output_counters
    )


def test_exit_outputs_include_boolean_and_distance_instance_counters() -> None:
    base = make_ema_pullback_strategy_spec()
    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=(
                    exit_rsi(instance_id="rsi_exit_base", period=3, long_exit_above=60.0),
                    exit_atr_stop_loss(atr_period=14, atr_multiplier=1.5),
                    exit_atr_take_profit(atr_period=14, atr_multiplier=4.0),
                ),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC")
    ohlcv = _ohlcv().reindex(idx).ffill()
    df = add_feature_columns_from_plan(ohlcv, plan)
    df[plan.anchor_columns["anchor"]] = df["close"]
    df[plan.rsi_columns[("base", 3)]] = [50.0, 70.0] * 15

    exit_outputs = build_exit_outputs_with_context_bundle(df, spec, plan)
    counters = {
        (item["instance_id"], item["output_type"], item.get("side")): item
        for item in exit_outputs.output_counters
    }

    assert counters[("rsi_exit_base", "boolean", "long")]["counters"]["signal_count"] == 15
    assert counters[("atr_stop_loss", "distance", None)]["counters"]["non_null_distance_count"] > 0
    assert counters[("atr_take_profit", "distance", None)]["counters"]["ready_count"] > 0


def test_build_signals_from_spec_can_emit_short_entries_when_enabled() -> None:
    spec = make_ema_pullback_strategy_spec(
        enabled_sides=("long", "short"),
        setup_lookback=3,
        setup_active_bars=3,
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    df = add_feature_columns_from_plan(_ohlcv(), plan)

    # Short stack + armed setup: untouched bars 0-2, touch at bar 4, reclaim short at bar 5.
    df["close"] = [95.0, 95.0, 95.0, 95.0, 101.0, 98.0, 97.0, 96.0]
    df["high"] = [95.0, 95.0, 95.0, 95.0, 101.0, 99.0, 98.0, 97.0]
    df["low"] = [94.0, 94.0, 94.0, 94.0, 98.0, 97.0, 96.0, 95.0]
    df[plan.anchor_columns["fast"]] = [90.0] * len(df)
    df[plan.anchor_columns["anchor"]] = [100.0] * len(df)
    df[plan.anchor_columns["slow"]] = [110.0] * len(df)

    signals = build_signals_from_spec(df, spec, plan)
    assert bool(signals.entries.any()) is False
    assert signals.short_entries.tolist() == [False, False, False, False, False, True, False, False]
    assert bool(signals.short_entries.isna().any()) is False


def test_blocker_and_signal_exit_composition_semantics() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    left = pd.Series([True, True, False, True], index=idx)
    right = pd.Series([True, False, True, True], index=idx)

    blockers = compose_blocker_signals((left, right))
    exits = compose_exit_signals((left, right), index=idx)

    assert blockers.tolist() == [True, False, False, True]
    assert exits.tolist() == [True, True, True, True]
