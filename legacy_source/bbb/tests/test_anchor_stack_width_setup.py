"""anchor_stack_width_setup component tests."""

from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.experiments.config_loader import load_strategy_config
from research.strategies.ema_pullback.component_builders import (
    anchor_stack_width_setup_spec,
    setup_anchor_stack_width,
    setup_rule,
    untouched_anchor_setup_spec,
)
from research.strategies.ema_pullback.components.registry import (
    ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
)
from research.strategies.ema_pullback.components.setup import (
    REASON_CURRENT_WIDTH_TOO_NARROW,
    REASON_INDICATOR_NOT_READY,
    REASON_RECENT_WIDTH_NEVER_EXPANDED,
    anchor_stack_width_setup_trace,
    build_anchor_stack_width_setup_counters,
)
from research.strategies.ema_pullback.execution.signal_trace import build_component_events
from research.strategies.ema_pullback.execution.signals import build_signals_from_spec
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.setup_runtime import compose_setup_masks
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec
from tests.test_external_config_loader import _bundle, _instance


def _frame(
    *,
    periods: int = 120,
    fast_offset: float = 5.0,
    slow_offset: float = -5.0,
    atr: float = 1.0,
) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=periods, freq="h", tz="UTC")
    close = pd.Series(100.0, index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1.0,
            "fast_ema": close + fast_offset,
            "anchor_ema": close,
            "slow_ema": close + slow_offset,
            "atr_col": atr,
        },
        index=idx,
    )


def test_inclusive_rolling_max_includes_current_bar() -> None:
    df = _frame(periods=5, fast_offset=5.0, slow_offset=-5.0, atr=1.0)
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=1.0,
        min_recent_width_atr=1.0,
        width_lookback_bars=3,
    )
    # width_atr = 10 on every bar; inclusive max at last bar is 10
    assert float(trace["recent_max_width_atr"].iloc[-1]) == pytest.approx(10.0)


def test_allowed_when_current_and_recent_thresholds_met() -> None:
    df = _frame()
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=2.0,
        min_recent_width_atr=4.0,
        width_lookback_bars=10,
    )
    assert trace["setup_allowed"].iloc[-1]
    assert trace["blocked_reason"].iloc[-1] == ""


def test_allowed_when_current_equals_recent_max() -> None:
    df = _frame()
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=2.0,
        min_recent_width_atr=10.0,
        width_lookback_bars=5,
    )
    last = len(df) - 1
    assert float(trace["current_width_atr"].iloc[last]) == float(
        trace["recent_max_width_atr"].iloc[last]
    )
    assert trace["setup_allowed"].iloc[last]


def test_blocks_current_width_too_narrow() -> None:
    df = _frame(fast_offset=0.5, slow_offset=-0.5, atr=1.0)
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=2.0,
        min_recent_width_atr=1.0,
        width_lookback_bars=5,
    )
    assert not trace["setup_allowed"].iloc[-1]
    assert trace["blocked_reason"].iloc[-1] == REASON_CURRENT_WIDTH_TOO_NARROW


def test_blocks_recent_width_never_expanded() -> None:
    idx = pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC")
    close = pd.Series(100.0, index=idx)
    fast = close.copy()
    slow = close.copy()
    fast.iloc[10:20] = close.iloc[10:20] + 20.0
    slow.iloc[10:20] = close.iloc[10:20] - 20.0
    fast.iloc[20:] = close.iloc[20:] + 0.5
    slow.iloc[20:] = close.iloc[20:] - 0.5
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1.0,
            "fast_ema": fast,
            "anchor_ema": close,
            "slow_ema": slow,
            "atr_col": 1.0,
        },
        index=idx,
    )
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=0.5,
        min_recent_width_atr=15.0,
        width_lookback_bars=5,
    )
    assert not trace["setup_allowed"].iloc[-1]
    assert trace["blocked_reason"].iloc[-1] == REASON_RECENT_WIDTH_NEVER_EXPANDED


def test_blocks_indicator_not_ready_on_nan() -> None:
    df = _frame(periods=10)
    df.loc[df.index[-1], "atr_col"] = float("nan")
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=1.0,
        min_recent_width_atr=1.0,
        width_lookback_bars=3,
    )
    assert not trace["setup_allowed"].iloc[-1]
    assert trace["blocked_reason"].iloc[-1] == REASON_INDICATOR_NOT_READY


def test_side_neutral_width() -> None:
    df = _frame()
    long_trace = anchor_stack_width_setup_trace(
        df, "fast_ema", "anchor_ema", "slow_ema", "atr_col",
        min_current_width_atr=2.0, min_recent_width_atr=4.0, width_lookback_bars=10, side="long",
    )
    short_trace = anchor_stack_width_setup_trace(
        df, "fast_ema", "anchor_ema", "slow_ema", "atr_col",
        min_current_width_atr=2.0, min_recent_width_atr=4.0, width_lookback_bars=10, side="short",
    )
    assert long_trace["setup_allowed"].equals(short_trace["setup_allowed"])


def test_build_counters_breakdown() -> None:
    df = _frame(periods=5, fast_offset=0.2, slow_offset=-0.2)
    trace = anchor_stack_width_setup_trace(
        df,
        "fast_ema",
        "anchor_ema",
        "slow_ema",
        "atr_col",
        min_current_width_atr=10.0,
        min_recent_width_atr=10.0,
        width_lookback_bars=2,
    )
    counters = build_anchor_stack_width_setup_counters(trace)
    assert counters["blocked_count"] > 0
    assert REASON_CURRENT_WIDTH_TOO_NARROW in counters["blocked_reason_breakdown"]


def test_feature_plan_includes_atr() -> None:
    spec = make_ema_pullback_strategy_spec(
        setups=(
            setup_rule(
                instance_id="anchor_stack_width",
                component_id=setup_anchor_stack_width(),
                params=anchor_stack_width_setup_spec(),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    cols = plan.setup_columns_for("anchor_stack_width")
    assert "atr" in cols
    assert any(f.kind == "atr" and f.period == 14 for f in plan.features)


def test_load_anchor_stack_width_config() -> None:
    instance = _instance("width_setup")
    strategy = instance["strategy"]
    assert isinstance(strategy, dict)
    strategy["setups"] = [
        {
            "instance_id": "anchor_stack_width",
            "component_id": "anchor_stack_width_setup",
            "params": {
                "atr_timeframe": "base",
                "atr_period": 14,
                "min_current_width_atr": 2.0,
                "min_recent_width_atr": 4.0,
                "width_lookback_bars": 80,
            },
        },
    ]
    loaded = load_strategy_config(_bundle([instance]))
    rule = loaded.specs[0].setups[0]
    assert rule.component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT
    assert rule.params.min_recent_width_atr == 4.0


def test_load_anchor_stack_width_config_with_htf_atr() -> None:
    instance = _instance("width_setup_htf")
    strategy = instance["strategy"]
    assert isinstance(strategy, dict)
    strategy["setups"] = [
        {
            "instance_id": "anchor_stack_width",
            "component_id": "anchor_stack_width_setup",
            "params": {
                "atr_timeframe": "1h",
                "atr_period": 14,
                "min_current_width_atr": 2.0,
                "min_recent_width_atr": 4.0,
                "width_lookback_bars": 80,
            },
        },
    ]
    loaded = load_strategy_config(_bundle([instance]))
    rule = loaded.specs[0].setups[0]
    assert rule.params.atr_timeframe == "1h"


def test_feature_plan_uses_configured_atr_timeframe() -> None:
    spec = make_ema_pullback_strategy_spec(
        setups=(
            setup_rule(
                instance_id="anchor_stack_width",
                component_id=setup_anchor_stack_width(),
                params=anchor_stack_width_setup_spec(atr_timeframe="1h", atr_period=14),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    cols = plan.setup_columns_for("anchor_stack_width")
    assert cols["atr"] == "atr_close_1h_14"
    assert any(
        f.kind == "atr" and f.timeframe == "1h" and f.period == 14 for f in plan.features
    )


def test_htf_atr_column_used_in_width_setup_trace() -> None:
    from dataclasses import replace

    spec = replace(
        make_ema_pullback_strategy_spec(),
        setups=(
            setup_rule(
                instance_id="anchor_stack_width",
                component_id=setup_anchor_stack_width(),
                params=anchor_stack_width_setup_spec(
                    atr_timeframe="4h",
                    atr_period=3,
                    min_current_width_atr=0.01,
                    min_recent_width_atr=0.01,
                    width_lookback_bars=3,
                ),
            ),
        ),
    )
    idx = pd.date_range("2024-01-01", periods=24, freq="h", tz="UTC")
    close = pd.Series([100.0 + float(i) * 0.5 for i in range(24)], index=idx)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    prepared = add_feature_columns_from_plan(df, plan)
    cols = plan.setup_columns_for("anchor_stack_width")
    assert cols["atr"] == "atr_close_4h_3"
    prepared[cols["fast"]] = close + 5.0
    prepared[cols["slow"]] = close - 5.0

    trace = anchor_stack_width_setup_trace(
        prepared,
        cols["fast"],
        cols["anchor"],
        cols["slow"],
        cols["atr"],
        min_current_width_atr=0.01,
        min_recent_width_atr=0.01,
        width_lookback_bars=3,
    )
    valid = prepared[cols["atr"]].notna()
    assert valid.any()
    pd.testing.assert_series_equal(
        trace["atr_value"].where(valid),
        prepared[cols["atr"]].where(valid),
        check_names=False,
    )
    base_atr_col = next(
        f.feature_id for f in plan.features if f.kind == "atr" and f.timeframe == "base"
    )
    both_valid = valid & prepared[base_atr_col].notna()
    assert not trace["atr_value"].where(both_valid).equals(
        prepared[base_atr_col].where(both_valid)
    )


def test_invalid_atr_timeframe_rejected() -> None:
    from research.strategies.ema_pullback.spec import AnchorStackWidthSetupSpec

    with pytest.raises(ValueError, match="unsupported timeframe"):
        AnchorStackWidthSetupSpec(atr_timeframe="2h")


def test_min_recent_below_min_current_config_accepted() -> None:
    from research.strategies.ema_pullback.spec import AnchorStackWidthSetupSpec

    spec = AnchorStackWidthSetupSpec(
        min_current_width_atr=4.0,
        min_recent_width_atr=1.0,
    )
    assert spec.min_current_width_atr == 4.0


def test_multi_setup_and_with_untouched() -> None:
    from dataclasses import replace

    spec = replace(
        make_ema_pullback_strategy_spec(enabled_sides=("long",)),
        setups=(
            setup_rule(
                instance_id="width",
                component_id=setup_anchor_stack_width(),
                params=anchor_stack_width_setup_spec(
                    min_current_width_atr=100.0,
                    min_recent_width_atr=100.0,
                ),
            ),
            setup_rule(
                instance_id="untouched",
                component_id=UNTOUCHED_ANCHOR_SETUP_COMPONENT,
                params=untouched_anchor_setup_spec(lookback=2, active_bars=1),
            ),
        ),
    )
    df = _frame()
    plan = build_feature_plan_from_strategy_spec(spec)
    prepared = add_feature_columns_from_plan(df, plan)
    width_only = compose_setup_masks(
        prepared, (spec.setups[0],), plan, anchor_col=plan.anchor_columns["anchor"], side="long"
    )
    combined = compose_setup_masks(
        prepared,
        spec.setups,
        plan,
        anchor_col=plan.anchor_columns["anchor"],
        side="long",
    )
    assert not width_only.iloc[-1]
    assert combined.sum() <= width_only.sum()


def test_component_events_two_per_allowed_episode() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="h", tz="UTC")
    close = pd.Series(100.0, index=idx)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )
    spec = make_ema_pullback_strategy_spec(
        setups=(
            setup_rule(
                instance_id="anchor_stack_width",
                component_id=setup_anchor_stack_width(),
                params=anchor_stack_width_setup_spec(
                    min_current_width_atr=1.0,
                    min_recent_width_atr=1.0,
                    width_lookback_bars=3,
                ),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    prepared = add_feature_columns_from_plan(df, plan)
    cols = plan.setup_columns_for("anchor_stack_width")
    spread = [2.0 if i in range(5, 13) else 0.2 for i in range(len(idx))]
    prepared[cols["fast"]] = close + pd.Series(spread, index=idx)
    prepared[cols["slow"]] = close - pd.Series(spread, index=idx)
    prepared[cols["atr"]] = 1.0
    times = [int(ts.timestamp()) for ts in prepared.index]
    events = build_component_events(prepared, spec, plan, times)
    width_events = [
        e
        for e in events
        if e.component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT and e.side == "long"
    ]
    starts = [e for e in width_events if e.event_type == "span_start"]
    ends = [e for e in width_events if e.event_type == "span_end"]
    assert len(starts) == 1
    assert len(ends) == 1
    assert starts[0].label == "Width ok"
    assert ends[0].label == "Width end"
    assert "Anchor stack width setup" in (starts[0].tooltip or "")
    assert len(width_events) == 2


def test_signals_emit_setup_counters() -> None:
    spec = make_ema_pullback_strategy_spec(
        setups=(
            setup_rule(
                instance_id="anchor_stack_width",
                component_id=setup_anchor_stack_width(),
                params=anchor_stack_width_setup_spec(),
            ),
        ),
    )
    df = _frame()
    plan = build_feature_plan_from_strategy_spec(spec)
    prepared = add_feature_columns_from_plan(df, plan)
    signals = build_signals_from_spec(prepared, spec, plan)
    width_counters = [
        c
        for c in signals.output_counters
        if c.get("component_id") == ANCHOR_STACK_WIDTH_SETUP_COMPONENT
    ]
    assert len(width_counters) == 1
    assert "allowed_count" in width_counters[0]["counters"]
    assert "blocked_reason_breakdown" in width_counters[0]["counters"]
