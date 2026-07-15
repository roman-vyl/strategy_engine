from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.strategies.ema_pullback.component_builders import (
    exit_atr_stop_loss,
    exit_atr_take_profit,
    exit_constant_usd_stop_loss,
    exit_constant_usd_take_profit,
    exit_rsi,
    exits_atr_default,
    trade_management,
)
from tests.ema_pullback_context_helpers import (
    build_exit_outputs_with_context_bundle,
    exit_policy_htf_consumption,
    htf_strategy_contexts,
)
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec


def _spec_with_exits(exits: tuple) -> object:
    base = make_ema_pullback_strategy_spec()
    return make_ema_pullback_strategy_spec(
        components=base.components,
        contexts=base.contexts,
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(always_on=exits),
        ),
    )


def _ohlcv(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = pd.Series([100.0 + float(i) for i in range(n)], index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )


def test_build_exit_outputs_supports_stop_loss_and_take_profit_distances() -> None:
    spec = make_ema_pullback_strategy_spec()
    plan = build_feature_plan_from_strategy_spec(spec)

    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    stop_dist = pd.Series([1.5, 3.0, 4.5, 6.0], index=idx)
    take_dist = pd.Series([4.0, 8.0, 12.0, 16.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            plan.exit_distance_columns["stop_loss"]: stop_dist,
            plan.exit_distance_columns["take_profit"]: take_dist,
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)
    pd.testing.assert_series_equal(exits.sl_stop, stop_dist / close, check_names=False)
    pd.testing.assert_series_equal(exits.tp_stop, take_dist / close, check_names=False)
    assert exits.exits.tolist() == [False, False, False, False]
    assert exits.short_exits.tolist() == [False, False, False, False]


def test_build_exit_outputs_constant_usd_distances() -> None:
    spec = _spec_with_exits(
        (
            exit_constant_usd_stop_loss(usd_distance=500.0),
            exit_constant_usd_take_profit(usd_distance=1200.0),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    assert plan.exit_distance_columns == {}

    df = _ohlcv(n=10)
    out = build_exit_outputs_with_context_bundle(df, spec, plan)
    close = df["close"].astype(float)
    pd.testing.assert_series_equal(
        out.sl_stop,
        pd.Series(500.0, index=df.index) / close,
        check_names=False,
    )
    pd.testing.assert_series_equal(
        out.tp_stop,
        pd.Series(1200.0, index=df.index) / close,
        check_names=False,
    )


def test_default_factory_exit_rules_match_atr_shortcut_defaults() -> None:
    spec = make_ema_pullback_strategy_spec()
    assert spec.trade_management.exit_policy.always_on.exits == exits_atr_default(
        atr_period=14,
        stop_atr_multiplier=1.5,
        take_atr_multiplier=4.0,
    )


def test_build_exit_outputs_skips_boolean_counters_for_disabled_trade_side() -> None:
    spec = make_ema_pullback_strategy_spec(
        enabled_sides=("long",),
        contexts=htf_strategy_contexts(fast_period=20, anchor_period=50, slow_period=200),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=(
                    exit_rsi(
                        instance_id="rsi_long_only",
                        timeframe="base",
                        period=14,
                        long_exit_above=70.0,
                        short_exit_below=30.0,
                    ),
                ),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            "rsi_close_base_14": [50.0, 75.0, 20.0, 50.0],
        },
        index=idx,
    )
    out = build_exit_outputs_with_context_bundle(df, spec, plan)
    boolean_counters = [c for c in out.output_counters if c["output_type"] == "boolean"]
    assert len(boolean_counters) == 1
    assert boolean_counters[0]["side"] == "long"
    assert out.attribution is not None
    short_series = out.attribution.short_signal_by_rule[0]
    assert short_series is not None
    assert not short_series.any()


def test_build_exit_outputs_attribution_matches_aggregated_stops() -> None:
    """Attribution context must come from the same single pass as portfolio stops."""

    spec = _spec_with_exits(
        (
            exit_atr_stop_loss(atr_period=14, atr_multiplier=1.5, instance_id="atr_sl_fast"),
            exit_atr_stop_loss(atr_period=14, atr_multiplier=2.0, instance_id="atr_sl_slow"),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    fast_stop = pd.Series([1.5, 1.5, 1.5, 1.5], index=idx)
    slow_stop = pd.Series([2.0, 2.0, 2.0, 2.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            plan.exit_distance_columns["atr_sl_fast"]: fast_stop,
            plan.exit_distance_columns["atr_sl_slow"]: slow_stop,
        },
        index=idx,
    )
    out = build_exit_outputs_with_context_bundle(df, spec, plan)
    assert out.attribution is not None
    ctx = out.attribution
    pd.testing.assert_series_equal(ctx.sl_stop_agg, out.sl_stop, check_names=False)
    pd.testing.assert_series_equal(ctx.distance_ratio_by_rule[0], fast_stop / close, check_names=False)
    pd.testing.assert_series_equal(ctx.distance_ratio_by_rule[1], slow_stop / close, check_names=False)


def test_build_exit_outputs_aggregates_repeated_distance_instances_by_kind() -> None:
    spec = _spec_with_exits(
        (
            exit_atr_stop_loss(atr_period=14, atr_multiplier=1.5, instance_id="atr_sl_fast"),
            exit_atr_stop_loss(atr_period=14, atr_multiplier=2.0, instance_id="atr_sl_slow"),
            exit_atr_take_profit(atr_period=14, atr_multiplier=4.0),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)

    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    fast_stop = pd.Series([1.5, 1.5, 1.5, 1.5], index=idx)
    slow_stop = pd.Series([2.0, 2.0, 2.0, 2.0], index=idx)
    take_dist = pd.Series([4.0, 4.0, 4.0, 4.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            plan.exit_distance_columns["atr_sl_fast"]: fast_stop,
            plan.exit_distance_columns["atr_sl_slow"]: slow_stop,
            plan.exit_distance_columns["atr_take_profit"]: take_dist,
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)

    pd.testing.assert_series_equal(exits.sl_stop, fast_stop / close, check_names=False)
    pd.testing.assert_series_equal(exits.tp_stop, take_dist / close, check_names=False)
    assert [counter["instance_id"] for counter in exits.output_counters] == [
        "atr_sl_fast",
        "atr_sl_slow",
        "atr_take_profit",
    ]


def test_build_exit_outputs_supports_only_stop_loss_distance() -> None:
    spec = _spec_with_exits((exit_atr_stop_loss(atr_period=14, atr_multiplier=1.5, instance_id="atr_sl_only"),))
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    stop_dist = pd.Series([1.5, 3.0, 4.5, 6.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            plan.exit_distance_columns["atr_sl_only"]: stop_dist,
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)
    pd.testing.assert_series_equal(exits.sl_stop, stop_dist / close, check_names=False)
    assert exits.tp_stop.isna().all()


def test_build_exit_outputs_supports_only_take_profit_distance() -> None:
    spec = _spec_with_exits(
        (
            exit_atr_take_profit(
                atr_period=14,
                atr_multiplier=4.0,
                instance_id="atr_tp_only",
            ),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    take_dist = pd.Series([4.0, 8.0, 12.0, 16.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            plan.exit_distance_columns["atr_tp_only"]: take_dist,
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)
    assert exits.sl_stop.isna().all()
    pd.testing.assert_series_equal(exits.tp_stop, take_dist / close, check_names=False)


def test_build_exit_outputs_supports_signal_only_exits() -> None:
    spec = _spec_with_exits(
        (
            exit_rsi(
                instance_id="rsi_signal_only",
                timeframe="base",
                period=14,
                long_exit_above=70.0,
                short_exit_below=30.0,
            ),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            "rsi_close_base_14": [50.0, 75.0, 20.0, 50.0],
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)
    assert exits.sl_stop.isna().all()
    assert exits.tp_stop.isna().all()
    assert exits.exits.tolist() == [False, True, False, False]


def test_build_exit_outputs_supports_signal_exit_with_stop_loss_distance() -> None:
    spec = _spec_with_exits(
        (
            exit_rsi(
                instance_id="rsi_exit_with_sl",
                timeframe="base",
                period=14,
                long_exit_above=70.0,
                short_exit_below=30.0,
            ),
            exit_atr_stop_loss(atr_period=14, atr_multiplier=1.5, instance_id="atr_sl_only"),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    stop_dist = pd.Series([1.5, 3.0, 4.5, 6.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            "rsi_close_base_14": [50.0, 75.0, 20.0, 50.0],
            plan.exit_distance_columns["atr_sl_only"]: stop_dist,
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)
    pd.testing.assert_series_equal(exits.sl_stop, stop_dist / close, check_names=False)
    assert exits.tp_stop.isna().all()
    assert exits.exits.tolist() == [False, True, False, False]


def test_build_exit_outputs_supports_signal_exit_with_take_profit_distance() -> None:
    spec = _spec_with_exits(
        (
            exit_rsi(
                instance_id="rsi_exit_with_tp",
                timeframe="base",
                period=14,
                long_exit_above=70.0,
                short_exit_below=30.0,
            ),
            exit_atr_take_profit(atr_period=14, atr_multiplier=4.0, instance_id="atr_tp_only"),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    take_dist = pd.Series([4.0, 8.0, 12.0, 16.0], index=idx)
    df = pd.DataFrame(
        {
            "close": close,
            "ema_close_base_200": close,
            "rsi_close_base_14": [50.0, 75.0, 20.0, 50.0],
            plan.exit_distance_columns["atr_tp_only"]: take_dist,
        },
        index=idx,
    )

    exits = build_exit_outputs_with_context_bundle(df, spec, plan)
    assert exits.sl_stop.isna().all()
    pd.testing.assert_series_equal(exits.tp_stop, take_dist / close, check_names=False)
    assert exits.exits.tolist() == [False, True, False, False]


def test_stop_ready_is_per_profile_not_global_sl_tp_requirement() -> None:
    """TP-only aligned profile must not require SL readiness on aligned bars (draft config shape)."""
    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(fast_period=20, anchor_period=50, slow_period=200),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=(),
                aligned=(exit_atr_take_profit(atr_period=14, atr_multiplier=4.0, instance_id="aligned_tp"),),
                countertrend=(exit_atr_stop_loss(atr_period=14, atr_multiplier=2.0, instance_id="counter_sl"),),
                neutral=(),
            )
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    df = add_feature_columns_from_plan(_ohlcv(120), plan)
    exits = build_exit_outputs_with_context_bundle(df, spec, plan)

    aligned_mask = exits.profile_long == "aligned"
    assert aligned_mask.any()
    assert exits.stop_ready_long[aligned_mask].any()
    expected = exits.tp_stop_by_profile["aligned"][aligned_mask].notna()
    pd.testing.assert_series_equal(
        exits.stop_ready_long[aligned_mask],
        expected,
        check_names=False,
    )


def test_feature_plan_does_not_require_atr_for_signal_only_exits() -> None:
    spec = _spec_with_exits(
        (
            exit_rsi(
                instance_id="rsi_signal_only",
                timeframe="base",
                period=14,
                long_exit_above=70.0,
                short_exit_below=30.0,
            ),
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)

    assert not any(feature.kind in {"atr", "atr_distance"} for feature in plan.features)

    df = add_feature_columns_from_plan(_ohlcv(), plan)
    assert all(feature.feature_id in df.columns for feature in plan.features)
    assert not any(
        column.startswith("atr_close_")
        for column in df.columns
        if column not in {"open", "high", "low", "close", "volume"}
    )
