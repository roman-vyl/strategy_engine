from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.strategies.ema_pullback.component_builders import (
    exit_policy,
    exit_constant_usd_stop_loss,
    exit_constant_usd_take_profit,
    trade_management,
)
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import (
    FeaturePlan,
    PlannedFeature,
    build_feature_plan_from_strategy_spec,
)
from research.strategies.ema_pullback.spec import (
    BlockerRuleSpec,
    ExitRuleSpec,
    RsiFeatureSpec,
)
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec


def _ohlcv(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = pd.Series([100.0 + float(i) * 0.5 for i in range(n)], index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )


def test_feature_plan_ids_follow_strategy_spec() -> None:
    spec = make_ema_pullback_strategy_spec()
    plan = build_feature_plan_from_strategy_spec(spec)
    ema_feats = [f for f in plan.features if f.kind == "ema"]
    assert {f.period for f in ema_feats} >= {
        spec.anchor_stack.fast.period,
        spec.anchor_stack.anchor.period,
        spec.anchor_stack.slow.period,
    }
    for f in ema_feats:
        assert f.feature_id == f"ema_close_{f.timeframe}_{f.period}"

    atr_feats = [f for f in plan.features if f.kind == "atr"]
    assert len(atr_feats) == 1
    atr_periods = {
        r.distance.period
        for r in spec.trade_management.exit_policy.always_on.exits
        if r.distance is not None
    }
    assert atr_feats[0].period in atr_periods
    assert atr_feats[0].feature_id == f"atr_close_{atr_feats[0].timeframe}_{atr_feats[0].period}"

    dist_feats = [f for f in plan.features if f.kind == "atr_distance"]
    distance_rules = [r for r in spec.trade_management.exit_policy.always_on.exits if r.distance is not None]
    assert len(dist_feats) == len(distance_rules)
    by_mult = {f.multiplier: f.feature_id for f in dist_feats}
    for rule in distance_rules:
        assert rule.distance is not None
        assert rule.distance.multiplier in by_mult
        assert by_mult[rule.distance.multiplier] == plan.exit_distance_columns[rule.exit_kind]


def test_add_feature_columns_from_plan_creates_expected_columns() -> None:
    spec = make_ema_pullback_strategy_spec()
    plan = build_feature_plan_from_strategy_spec(spec)
    df = add_feature_columns_from_plan(_ohlcv(40), plan)
    for f in plan.features:
        assert f.feature_id in df.columns


def test_atr_distance_columns_follow_plan_multipliers() -> None:
    spec = make_ema_pullback_strategy_spec()
    plan = build_feature_plan_from_strategy_spec(spec)
    df = add_feature_columns_from_plan(_ohlcv(40), plan)
    atr_col = next(f.feature_id for f in plan.features if f.kind == "atr")
    atr = df[atr_col].astype(float)
    valid = atr.notna()
    for f in plan.features:
        if f.kind != "atr_distance" or f.multiplier is None or f.base_feature_id is None:
            continue
        col = df[f.feature_id].astype(float)
        m = float(f.multiplier)
        pd.testing.assert_series_equal(col.where(valid), (m * atr).where(valid), check_names=False)


def test_base_rsi_feature_plan_and_calculation() -> None:
    base = make_ema_pullback_strategy_spec()
    spec = make_ema_pullback_strategy_spec(
        components=replace(
            base.components,
            blockers=(
                BlockerRuleSpec(
                    instance_id="rsi_base",
                    component_id="rsi_lookback_extreme_blocker",
                    rsi=RsiFeatureSpec(timeframe="base", period=3),
                    long_block_above=80.0,
                    short_block_below=20.0,
                ),
            ),
        ),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy(
                always_on=(
                    ExitRuleSpec(
                        instance_id="rsi_exit_base",
                        component_id="rsi_signal_exit",
                        exit_kind="signal",
                        rsi=RsiFeatureSpec(timeframe="base", period=3),
                        long_exit_above=70.0,
                        short_exit_below=30.0,
                    ),
                    *base.trade_management.exit_policy.always_on.exits,
                ),
                aligned=(),
                countertrend=(),
                neutral=(),
            )
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    rsi_col = plan.rsi_columns[("base", 3)]
    assert rsi_col == "rsi_close_base_3"
    assert any(f.kind == "rsi" and f.feature_id == rsi_col for f in plan.features)

    df = add_feature_columns_from_plan(_ohlcv(8), plan)
    assert rsi_col in df.columns
    assert df[rsi_col].iloc[:3].isna().all()
    assert df[rsi_col].iloc[3:].notna().all()
    assert (df[rsi_col].iloc[3:] == 100.0).all()


def test_mtf_ema_and_rsi_align_only_after_completed_candle() -> None:
    idx = pd.date_range("2024-01-01", periods=12, freq="h", tz="UTC")
    close = pd.Series([float(i) for i in range(1, 13)], index=idx)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )
    plan = FeaturePlan(
        features=(
            PlannedFeature(
                feature_id="ema_close_4h_2",
                kind="ema",
                source="close",
                timeframe="4h",
                period=2,
                base_feature_id=None,
                multiplier=None,
            ),
            PlannedFeature(
                feature_id="rsi_close_4h_1",
                kind="rsi",
                source="close",
                timeframe="4h",
                period=1,
                base_feature_id=None,
                multiplier=None,
            ),
        ),
        anchor_columns={},
        exit_distance_columns={},
        rsi_columns={("4h", 1): "rsi_close_4h_1"},
        htf_context_columns_by_ref={},
    )

    out = add_feature_columns_from_plan(df, plan)

    assert out["ema_close_4h_2"].iloc[:4].isna().all()
    assert out["ema_close_4h_2"].iloc[4:8].tolist() == [4.0, 4.0, 4.0, 4.0]
    assert out["ema_close_4h_2"].iloc[8] == pytest.approx(20.0 / 3.0)

    assert out["rsi_close_4h_1"].iloc[:8].isna().all()
    assert out["rsi_close_4h_1"].iloc[8:].tolist() == [100.0, 100.0, 100.0, 100.0]


def test_mtf_atr_distance_feature_uses_distance_timeframe() -> None:
    plan = FeaturePlan(
        features=(
            PlannedFeature(
                feature_id="atr_close_4h_3",
                kind="atr",
                source="close",
                timeframe="4h",
                period=3,
                base_feature_id=None,
                multiplier=None,
            ),
            PlannedFeature(
                feature_id="atr_close_4h_3_x1_5",
                kind="atr_distance",
                source=None,
                timeframe="4h",
                period=None,
                base_feature_id="atr_close_4h_3",
                multiplier=1.5,
            ),
        ),
        anchor_columns={},
        exit_distance_columns={"atr_sl_4h": "atr_close_4h_3_x1_5"},
        rsi_columns={},
        htf_context_columns_by_ref={},
    )
    out = add_feature_columns_from_plan(_ohlcv(24), plan)
    assert "atr_close_4h_3" in out.columns
    assert "atr_close_4h_3_x1_5" in out.columns
    valid = out["atr_close_4h_3"].notna()
    pd.testing.assert_series_equal(
        out["atr_close_4h_3_x1_5"].where(valid),
        (out["atr_close_4h_3"] * 1.5).where(valid),
        check_names=False,
    )


def test_feature_plan_skips_atr_when_only_constant_usd_exits() -> None:
    spec = make_ema_pullback_strategy_spec(
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy(
                always_on=(
                    exit_constant_usd_stop_loss(usd_distance=500.0),
                    exit_constant_usd_take_profit(usd_distance=1200.0),
                ),
                aligned=(),
                countertrend=(),
                neutral=(),
            )
        )
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    assert plan.exit_distance_columns == {}
    kinds = {f.kind for f in plan.features}
    assert "atr" not in kinds
    assert "atr_distance" not in kinds
