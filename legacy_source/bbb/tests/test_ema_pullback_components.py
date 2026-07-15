from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.strategies.ema_pullback.components import resolve_component
from research.strategies.ema_pullback.spec import (
    BlockerRuleSpec,
    ExitRuleSpec,
    RsiFeatureSpec,
)
from research.strategies.ema_pullback.components.setup import (
    ema_bounce_counter_setup_trace,
)


def _frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "close": [99.0, 100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [101.0, 99.0, 103.0, 104.0],
            "ema_close_base_20": [11.0, 12.0, 10.0, 14.0],
            "ema_close_base_200": [10.0, 11.0, 10.0, 13.0],
            "ema_close_base_1000": [9.0, 10.0, 9.0, 12.0],
        },
        index=idx,
    )


def _untouched_setup_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
    anchor = 100.0
    return pd.DataFrame(
        {
            "close": [105.0, 105.0, 105.0, 105.0, 101.0, 101.0, 101.0, 101.0],
            "low": [105.0, 105.0, 105.0, 105.0, 99.0, 101.0, 102.0, 103.0],
            "high": [106.0, 106.0, 106.0, 106.0, 102.0, 102.0, 103.0, 104.0],
            "ema_close_base_200": [anchor] * 8,
        },
        index=idx,
    )


def test_registry_resolves_new_stage10_components() -> None:
    assert callable(resolve_component("direction", "ema_anchor_stack_trend").func)
    assert callable(resolve_component("blockers", "no_blockers").func)
    assert callable(resolve_component("blockers", "counter_candle_blocker").func)
    assert callable(resolve_component("blockers", "rsi_lookback_extreme_blocker").func)
    assert callable(resolve_component("setup", "untouched_anchor_setup").func)
    assert callable(resolve_component("setup", "ema_bounce_counter_setup").func)
    assert callable(resolve_component("setup", "anchor_stack_width_setup").func)
    assert callable(resolve_component("trigger", "reclaim_anchor").func)
    assert callable(resolve_component("trigger", "strong_reclaim_anchor").func)
    assert callable(resolve_component("trigger", "touch_anchor").func)
    assert callable(resolve_component("exits", "no_signal_exit").func)
    assert callable(resolve_component("exits", "rsi_signal_exit").func)
    assert callable(resolve_component("exits", "atr_stop_loss").func)
    assert callable(resolve_component("exits", "atr_take_profit").func)
    assert callable(resolve_component("risk", "no_risk_filter").func)


def test_direction_component_uses_columns_not_period_constants() -> None:
    df = _frame()
    fn = resolve_component("direction", "ema_anchor_stack_trend").func
    out = fn(df, "ema_close_base_20", "ema_close_base_200", "ema_close_base_1000")
    assert out.tolist() == [True, True, False, True]


def test_direction_component_supports_short_side() -> None:
    df = _frame()
    fn = resolve_component("direction", "ema_anchor_stack_trend").func
    out = fn(df, "ema_close_base_1000", "ema_close_base_200", "ema_close_base_20", side="short")
    assert out.tolist() == [True, True, False, True]


def test_setup_trigger_exit_risk_components_shape() -> None:
    df = _frame()
    setup = resolve_component("setup", "untouched_anchor_setup").func(
        df, "ema_close_base_200", 50, 3
    )
    trigger = resolve_component("trigger", "reclaim_anchor").func(df, "ema_close_base_200", 1)
    exits = resolve_component("exits", "no_signal_exit").func(df, side="short")
    blockers = resolve_component("blockers", "no_blockers").func(df, side="short")
    risk = resolve_component("risk", "no_risk_filter").func(df, side="short")
    assert len(setup) == len(df)
    assert len(trigger) == len(df)
    assert bool(exits.any()) is False
    assert bool(blockers.all()) is True
    assert bool(risk.all()) is True


def test_untouched_anchor_setup_long_reference_example() -> None:
    df = _untouched_setup_frame()
    fn = resolve_component("setup", "untouched_anchor_setup").func
    out = fn(df, "ema_close_base_200", lookback=3, active_bars=3, side="long")
    assert out.tolist() == [False, False, False, True, True, True, True, False]


def test_untouched_anchor_setup_long_warmup_false() -> None:
    df = _untouched_setup_frame()
    fn = resolve_component("setup", "untouched_anchor_setup").func
    out = fn(df, "ema_close_base_200", lookback=3, active_bars=3, side="long")
    assert out.iloc[:3].tolist() == [False, False, False]


def test_untouched_anchor_setup_long_armed_before_touch() -> None:
    df = _untouched_setup_frame()
    fn = resolve_component("setup", "untouched_anchor_setup").func
    out = fn(df, "ema_close_base_200", lookback=3, active_bars=3, side="long")
    assert bool(out.iloc[3]) is True
    assert bool(out.iloc[2]) is False


def test_untouched_anchor_setup_long_first_touch_true() -> None:
    df = _untouched_setup_frame()
    fn = resolve_component("setup", "untouched_anchor_setup").func
    out = fn(df, "ema_close_base_200", lookback=3, active_bars=3, side="long")
    assert bool(out.iloc[4]) is True


def test_untouched_anchor_setup_active_bars_one() -> None:
    df = _untouched_setup_frame()
    fn = resolve_component("setup", "untouched_anchor_setup").func
    out = fn(df, "ema_close_base_200", lookback=3, active_bars=1, side="long")
    assert out.tolist() == [False, False, False, True, True, False, False, False]


def test_untouched_anchor_setup_short_mirror() -> None:
    idx = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
    anchor = 100.0
    df = pd.DataFrame(
        {
            "close": [95.0, 95.0, 95.0, 95.0, 99.0, 99.0, 99.0, 99.0],
            "high": [95.0, 95.0, 95.0, 95.0, 101.0, 99.0, 98.0, 97.0],
            "low": [94.0, 94.0, 94.0, 94.0, 98.0, 98.0, 97.0, 96.0],
            "ema_close_base_200": [anchor] * 8,
        },
        index=idx,
    )
    fn = resolve_component("setup", "untouched_anchor_setup").func
    out = fn(df, "ema_close_base_200", lookback=3, active_bars=3, side="short")
    assert out.tolist() == [False, False, False, True, True, True, True, False]


def _ema_bounce_counter_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
    anchor = 100.0
    return pd.DataFrame(
        {
            "close": [105.0] * 8,
            "low": [104.0, 99.0, 104.0, 99.0, 99.0, 104.0, 104.0, 104.0],
            "high": [106.0] * 8,
            "ema_fast": [110.0] * 8,
            "ema_anchor": [anchor] * 8,
            "ema_slow": [90.0] * 8,
        },
        index=idx,
    )


def test_ema_bounce_counter_inclusive_lookback_and_final_touch_guard() -> None:
    trace = ema_bounce_counter_setup_trace(
        _ema_bounce_counter_frame(),
        "ema_fast",
        "ema_anchor",
        "ema_slow",
        max_bounces=3,
        touch_lookback_bars=3,
        side="long",
    )

    # First window starts at index 1 and is active for 1,2,3. Raw touch at
    # final active bar 3 is ignored; a new pending can start only at 4.
    assert trace["pending_bounce_start"].tolist() == [
        False,
        True,
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    assert trace["pending_bounce_end"].tolist() == [
        False,
        False,
        False,
        True,
        False,
        False,
        True,
        False,
    ]
    assert trace["completed_bounce_count"].tolist() == [0, 0, 0, 0, 1, 1, 1, 2]


def test_ema_bounce_counter_blocks_after_limit_completion() -> None:
    trace = ema_bounce_counter_setup_trace(
        _ema_bounce_counter_frame(),
        "ema_fast",
        "ema_anchor",
        "ema_slow",
        max_bounces=1,
        touch_lookback_bars=3,
        side="long",
    )

    assert trace["setup_allowed"].tolist() == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert trace["pending_bounce_start"].tolist() == [
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


def test_bounce_counter_feature_plan_uses_anchor_stack_columns() -> None:
    from dataclasses import replace

    from research.strategies.ema_pullback.component_builders import (
        anchor_stack_width_setup_spec,
        ema_bounce_counter_setup_spec,
        setup_rule,
    )
    from research.strategies.ema_pullback.features.plan import (
        _ema_feature_id,
        build_feature_plan_from_strategy_spec,
    )
    from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec

    spec = replace(
        make_ema_pullback_strategy_spec(
            fast_period=50,
            anchor_period=200,
            slow_period=500,
        ),
        setups=(
            setup_rule(
                instance_id="bounce_counter",
                component_id="ema_bounce_counter_setup",
                params=ema_bounce_counter_setup_spec(max_bounces=3),
            ),
            setup_rule(
                instance_id="anchor_stack_width",
                component_id="anchor_stack_width_setup",
                params=anchor_stack_width_setup_spec(),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    stack = spec.anchor_stack
    expected_fast = _ema_feature_id(stack.fast.timeframe, stack.fast.period)
    bounce_cols = plan.setup_columns_for("bounce_counter")
    width_cols = plan.setup_columns_for("anchor_stack_width")
    assert bounce_cols == {
        "fast": expected_fast,
        "anchor": _ema_feature_id(stack.anchor.timeframe, stack.anchor.period),
        "slow": _ema_feature_id(stack.slow.timeframe, stack.slow.period),
    }
    assert width_cols["fast"] == expected_fast
    ema_features = [f for f in plan.features if f.kind == "ema"]
    assert len(ema_features) == 3


def test_ema_bounce_counter_short_side_mirror() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "close": [95.0] * 5,
            "low": [94.0] * 5,
            "high": [96.0, 101.0, 96.0, 96.0, 96.0],
            "ema_fast": [90.0] * 5,
            "ema_anchor": [100.0] * 5,
            "ema_slow": [110.0] * 5,
        },
        index=idx,
    )
    trace = ema_bounce_counter_setup_trace(
        df,
        "ema_fast",
        "ema_anchor",
        "ema_slow",
        max_bounces=3,
        touch_lookback_bars=2,
        side="short",
    )

    assert trace["trend_active"].tolist() == [True, True, True, True, True]
    assert trace["armed"].tolist() == [True, True, True, True, True]
    assert trace["raw_touch"].tolist() == [False, True, False, False, False]
    assert trace["pending_bounce_start"].tolist() == [False, True, False, False, False]


def _reclaim_fn():
    return resolve_component("trigger", "reclaim_anchor").func


def test_reclaim_anchor_current_wick_does_not_count() -> None:
    """Anti-lookahead: same-bar wick + reclaim without prior probe must not fire."""
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [10.5, 10.5, 9.5],
            "high": [11.0, 11.0, 11.0],
            "close": [10.5, 10.5, 10.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    fn = _reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="long").tolist() == [False, False, False]


def test_reclaim_anchor_long_prior_probe_and_reclaim() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0],
            "close": [10.5, 10.5, 10.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    fn = _reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="long").tolist() == [False, True, False]


def test_reclaim_anchor_long_no_prior_probe() -> None:
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [10.5, 10.5],
            "high": [11.0, 11.0],
            "close": [10.5, 10.5],
            "ema_close_base_200": [anchor, anchor],
        },
        index=idx,
    )
    fn = _reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="long").tolist() == [False, False]


def test_reclaim_anchor_long_prior_wick_despite_prior_close_above_anchor() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0],
            "close": [10.5, 11.0, 10.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    fn = _reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="long").tolist() == [False, True, False]


def test_reclaim_anchor_short_mirror() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.0, 9.0, 9.0],
            "high": [10.5, 9.5, 9.5],
            "close": [9.5, 9.5, 9.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    fn = _reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="short").tolist() == [False, True, False]


def test_reclaim_anchor_lookback_two_probe_at_t_minus_two() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [10.5, 9.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0, 11.0],
            "close": [10.5, 10.5, 9.5, 10.5],
            "ema_close_base_200": [anchor] * 4,
        },
        index=idx,
    )
    fn = _reclaim_fn()
    # Probe at bar 1; reclaim only at bar 3 (lookback=2 window bars 1-2).
    assert fn(df, "ema_close_base_200", 2, side="long").tolist() == [False, False, False, True]


def test_reclaim_anchor_probe_outside_lookback_window() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.5, 10.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0, 11.0],
            "close": [10.5, 10.5, 9.5, 10.5],
            "ema_close_base_200": [anchor] * 4,
        },
        index=idx,
    )
    fn = _reclaim_fn()
    # Probe only at bar 0; at bar 3 lookback=2 prior window is bars 1-2 — no probe.
    assert fn(df, "ema_close_base_200", 2, side="long").tolist() == [False, False, False, False]


def _strong_reclaim_fn():
    return resolve_component("trigger", "strong_reclaim_anchor").func


def test_strong_reclaim_anchor_long_prior_close_probe_and_reclaim() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [10.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0],
            "close": [9.5, 10.5, 10.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    fn = _strong_reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="long").tolist() == [False, True, False]


def test_strong_reclaim_anchor_long_wick_probe_without_close_probe_is_false() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0],
            "close": [10.5, 11.0, 10.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    reclaim = _reclaim_fn()
    strong = _strong_reclaim_fn()
    assert reclaim(df, "ema_close_base_200", 1, side="long").tolist() == [False, True, False]
    assert strong(df, "ema_close_base_200", 1, side="long").tolist() == [False, False, False]


def test_strong_reclaim_anchor_short_prior_close_probe_and_reclaim() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.0, 9.0, 9.0],
            "high": [10.5, 10.5, 10.5],
            "close": [10.5, 9.5, 9.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    fn = _strong_reclaim_fn()
    assert fn(df, "ema_close_base_200", 1, side="short").tolist() == [False, True, False]


def test_strong_reclaim_anchor_short_wick_probe_without_close_probe_is_false() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [9.0, 9.0, 9.0],
            "high": [10.5, 9.5, 9.5],
            "close": [9.5, 9.5, 9.5],
            "ema_close_base_200": [anchor, anchor, anchor],
        },
        index=idx,
    )
    reclaim = _reclaim_fn()
    strong = _strong_reclaim_fn()
    assert reclaim(df, "ema_close_base_200", 1, side="short").tolist() == [False, True, False]
    assert strong(df, "ema_close_base_200", 1, side="short").tolist() == [False, False, False]


def test_strong_reclaim_anchor_lookback_two_close_probe_at_t_minus_two() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [10.5, 10.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0, 11.0],
            "close": [10.5, 9.5, 9.5, 10.5],
            "ema_close_base_200": [anchor] * 4,
        },
        index=idx,
    )
    fn = _strong_reclaim_fn()
    # Close probe at bar 1; reclaim only at bar 3 (lookback=2 prior window bars 1-2).
    assert fn(df, "ema_close_base_200", 2, side="long").tolist() == [False, False, False, True]


def test_strong_reclaim_anchor_close_probe_outside_lookback_window() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    anchor = 10.0
    df = pd.DataFrame(
        {
            "low": [10.5, 10.5, 10.5, 10.5],
            "high": [11.0, 11.0, 11.0, 11.0],
            "close": [9.5, 10.5, 10.5, 10.5],
            "ema_close_base_200": [anchor] * 4,
        },
        index=idx,
    )
    fn = _strong_reclaim_fn()
    # Close probe only at bar 0; at bar 3 lookback=2 prior window is bars 1-2 — no probe.
    out = fn(df, "ema_close_base_200", 2, side="long").tolist()
    assert out[3] is False


def test_touch_anchor_trigger_supports_long_and_short_sides() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "high": [11.0, 12.0, 9.5, 10.5],
            "low": [10.5, 9.5, 8.5, 10.1],
            "close": [9.8, 10.5, 9.0, 9.8],
            "ema_close_base_200": [10.0, 10.0, 10.0, 10.0],
        },
        index=idx,
    )
    fn = resolve_component("trigger", "touch_anchor").func
    assert fn(df, "ema_close_base_200", side="long").tolist() == [False, True, False, False]
    assert fn(df, "ema_close_base_200", side="short").tolist() == [True, False, False, True]


def test_counter_candle_blocker_supports_long_and_short_sides() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0, 10.0],
            "close": [11.0, 9.0, 10.0, 8.0],
        },
        index=idx,
    )
    fn = resolve_component("blockers", "counter_candle_blocker").func
    assert fn(df, side="long").tolist() == [True, False, True, False]
    assert fn(df, side="short").tolist() == [False, True, True, True]


def _rsi_lookback_blocker_allowed(
    rsi_values: list[float],
    side: str,
    *,
    lookback: int = 3,
    long_block_above: float = 80.0,
    short_block_below: float = 20.0,
) -> list[bool]:
    idx = pd.date_range("2024-01-01", periods=len(rsi_values), freq="h", tz="UTC")
    df = pd.DataFrame({"rsi_close_base_14": rsi_values}, index=idx)
    rule = BlockerRuleSpec(
        instance_id="rsi_base",
        component_id="rsi_lookback_extreme_blocker",
        rsi=RsiFeatureSpec(timeframe="base", period=14),
        lookback=lookback,
        long_block_above=long_block_above,
        short_block_below=short_block_below,
    )
    fn = resolve_component("blockers", "rsi_lookback_extreme_blocker").func
    return fn(df, side=side, rule=rule, rsi_col="rsi_close_base_14").tolist()


def test_rsi_lookback_extreme_blocker_long_blocked_after_overbought_in_lookback() -> None:
    assert _rsi_lookback_blocker_allowed(
        [75.0, 85.0, 50.0], "long", lookback=3, long_block_above=80.0
    ) == [True, False, False]


def test_rsi_lookback_extreme_blocker_long_not_blocked_on_low_rsi() -> None:
    assert _rsi_lookback_blocker_allowed([25.0, 28.0, 29.0], "long", long_block_above=80.0) == [
        True,
        True,
        True,
    ]


def test_rsi_lookback_extreme_blocker_short_blocked_after_oversold_in_lookback() -> None:
    assert _rsi_lookback_blocker_allowed(
        [50.0, 15.0, 40.0], "short", lookback=3, short_block_below=20.0
    ) == [True, False, False]


def test_rsi_lookback_extreme_blocker_short_not_blocked_on_high_rsi() -> None:
    assert _rsi_lookback_blocker_allowed([75.0, 80.0, 85.0], "short", short_block_below=20.0) == [
        True,
        True,
        True,
    ]


def test_rsi_lookback_extreme_blocker_lookback_catches_prior_bar_extreme() -> None:
    assert _rsi_lookback_blocker_allowed(
        [90.0, 50.0, 50.0], "long", lookback=2, long_block_above=80.0
    ) == [False, False, True]


def test_rsi_signal_exit_uses_prepared_rsi_column() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame({"rsi_close_base_14": [20.0, 40.0, 80.0, 60.0]}, index=idx)
    rule = ExitRuleSpec(
        instance_id="rsi_exit_base",
        component_id="rsi_signal_exit",
        exit_kind="signal",
        rsi=RsiFeatureSpec(timeframe="base", period=14),
        long_exit_above=70.0,
        short_exit_below=30.0,
    )
    fn = resolve_component("exits", "rsi_signal_exit").func
    assert fn(df, side="long", rule=rule, rsi_col="rsi_close_base_14").tolist() == [
        False,
        False,
        True,
        False,
    ]
    assert fn(df, side="short", rule=rule, rsi_col="rsi_close_base_14").tolist() == [
        True,
        False,
        False,
        False,
    ]


def test_resolve_component_fails_for_unknown_values() -> None:
    with pytest.raises(ValueError, match="unknown component role"):
        resolve_component("unknown", "x")
    with pytest.raises(ValueError, match="unknown component_id"):
        resolve_component("trigger", "unknown")
