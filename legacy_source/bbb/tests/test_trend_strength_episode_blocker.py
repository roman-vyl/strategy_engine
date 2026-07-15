"""Tests for trend_strength_episode_blocker."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.strategies.ema_pullback.component_builders import (
    blocker_trend_strength_episode,
    component_stack,
)
from research.strategies.ema_pullback.components.trend_strength_episode import (
    REASON_CURRENT_ADX_TOO_LOW,
    REASON_INDICATOR_NOT_READY,
    REASON_NO_RECENT_PEAK,
    REASON_OPPOSITE_DI_FLIP,
    REASON_PEAK_TOO_OLD,
    build_trend_strength_blocker_counters,
    trend_strength_episode_blocker_trace,
)
from research.strategies.ema_pullback.features.calculations import (
    _compute_adx_dmi,
    _wilder_rma,
    add_feature_columns_from_plan,
)
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.spec import TrendStrengthEpisodeBlockerParams
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec

_ADX_DMI_COLS = {
    "adx": "adx_close_base_14",
    "di_plus": "di_plus_close_base_14",
    "di_minus": "di_minus_close_base_14",
}


def _synthetic_df(n: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    trend = np.linspace(100.0, 130.0, n)
    noise = np.sin(np.linspace(0, 12, n)) * 0.5
    close = trend + noise
    high = close + 1.0
    low = close - 1.0
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": 1.0},
        index=idx,
    )


def _prepare(df: pd.DataFrame, rule) -> tuple[pd.DataFrame, dict[str, str]]:
    spec = make_ema_pullback_strategy_spec(
        variant="test",
        components=component_stack(blockers=(rule,)),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    out = add_feature_columns_from_plan(df, plan)
    cols = plan.adx_dmi_columns_for(rule.trend_strength)
    return out, cols


def _trace(df: pd.DataFrame, rule, cols: dict[str, str], *, side: str = "long"):
    return trend_strength_episode_blocker_trace(
        df,
        side=side,
        rule=rule,
        adx_col=cols["adx"],
        di_plus_col=cols["di_plus"],
        di_minus_col=cols["di_minus"],
    )


def test_min_adx_peak_must_be_positive() -> None:
    with pytest.raises(ValueError, match="min_adx_peak"):
        TrendStrengthEpisodeBlockerParams(min_adx_peak=0)


def test_wilder_rma_constant_series_stays_flat_after_seed() -> None:
    period = 14
    values = pd.Series([5.0] * 30)
    smoothed = _wilder_rma(values, period=period)
    first_finite = int(np.argmax(np.isfinite(smoothed.to_numpy())))
    tail = smoothed.iloc[first_finite:].to_numpy()
    assert np.allclose(tail, 5.0, rtol=0, atol=1e-9)


def test_adx_dmi_warmup_not_finite_on_early_bars() -> None:
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    close = np.linspace(100.0, 130.0, n)
    high = close + 1.0
    low = close - 1.0
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": 1.0},
        index=idx,
    )
    period = 14
    adx, di_plus, di_minus = _compute_adx_dmi(
        df["high"], df["low"], df["close"], period=period
    )
    assert np.isnan(adx.iloc[0])
    assert np.isnan(adx.iloc[1])
    first_finite = int(np.argmax(np.isfinite(adx.to_numpy())))
    assert first_finite >= 2 * period - 2
    assert np.isfinite(adx.iloc[first_finite])
    assert 0.0 <= float(adx.iloc[first_finite]) <= 100.0


def test_rejects_non_base_timeframe() -> None:
    with pytest.raises(ValueError, match="timeframe"):
        TrendStrengthEpisodeBlockerParams(timeframe="1h")


def test_no_recent_peak_blocks_long() -> None:
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 15.0)
    di_plus = np.full(n, 25.0)
    di_minus = np.full(n, 10.0)
    fast = np.linspace(110, 120, n)
    anchor = np.linspace(105, 115, n)
    slow = np.linspace(100, 110, n)
    df = pd.DataFrame(
        {
            "open": fast,
            "high": fast + 1,
            "low": fast - 1,
            "close": fast,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
            "ema_close_base_50": fast,
            "ema_close_base_200": anchor,
            "ema_close_base_500": slow,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(
        instance_id="ts",
        min_adx_peak=25.0,
        peak_lookback_bars=20,
    )
    trace = _trace(df, rule, _ADX_DMI_COLS)
    assert trace["blocked_reason"].iloc[-1] == REASON_NO_RECENT_PEAK
    assert not trace["allowed"].iloc[-1]


def test_most_recent_qualifying_bar_not_local_max() -> None:
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 30.0)
    adx[-2] = 28.0
    adx[-1] = 20.0
    di_plus = np.full(n, 30.0)
    di_minus = np.full(n, 10.0)
    fast = np.linspace(110, 120, n)
    anchor = np.linspace(105, 115, n)
    slow = np.linspace(100, 110, n)
    df = pd.DataFrame(
        {
            "open": fast,
            "high": fast + 1,
            "low": fast - 1,
            "close": fast,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
            "ema_close_base_50": fast,
            "ema_close_base_200": anchor,
            "ema_close_base_500": slow,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(
        instance_id="ts",
        min_adx_peak=25.0,
        peak_lookback_bars=10,
        max_bars_since_peak=10,
        min_current_adx=20.0,
    )
    trace = _trace(df, rule, _ADX_DMI_COLS)
    assert trace["adx_peak_idx"].iloc[-1] == n - 2
    assert trace["allowed"].iloc[-1]


def test_peak_too_old() -> None:
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 10.0)
    adx[40] = 30.0
    di_plus = np.full(n, 30.0)
    di_minus = np.full(n, 10.0)
    fast = np.linspace(110, 120, n)
    anchor = np.linspace(105, 115, n)
    slow = np.linspace(100, 110, n)
    df = pd.DataFrame(
        {
            "open": fast,
            "high": fast + 1,
            "low": fast - 1,
            "close": fast,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
            "ema_close_base_50": fast,
            "ema_close_base_200": anchor,
            "ema_close_base_500": slow,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(
        instance_id="ts",
        min_adx_peak=25.0,
        peak_lookback_bars=20,
        max_bars_since_peak=5,
        min_current_adx=12.0,
    )
    trace = _trace(df, rule, _ADX_DMI_COLS)
    assert trace["blocked_reason"].iloc[-1] == REASON_PEAK_TOO_OLD


def test_opposite_di_flip_long() -> None:
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 30.0)
    di_plus = np.full(n, 30.0)
    di_minus = np.full(n, 10.0)
    di_plus[-1] = 5.0
    di_minus[-1] = 20.0
    fast = np.linspace(110, 120, n)
    anchor = np.linspace(105, 115, n)
    slow = np.linspace(100, 110, n)
    df = pd.DataFrame(
        {
            "open": fast,
            "high": fast + 1,
            "low": fast - 1,
            "close": fast,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
            "ema_close_base_50": fast,
            "ema_close_base_200": anchor,
            "ema_close_base_500": slow,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(
        instance_id="ts",
        block_on_opposite_di_flip=True,
        opposite_di_margin=5.0,
    )
    trace = _trace(df, rule, _ADX_DMI_COLS)
    assert trace["blocked_reason"].iloc[-1] == REASON_OPPOSITE_DI_FLIP


def test_counter_breakdown_sums_to_blocked_count() -> None:
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 15.0)
    di_plus = np.full(n, 25.0)
    di_minus = np.full(n, 10.0)
    fast = np.linspace(110, 120, n)
    anchor = np.linspace(105, 115, n)
    slow = np.linspace(100, 110, n)
    df = pd.DataFrame(
        {
            "open": fast,
            "high": fast + 1,
            "low": fast - 1,
            "close": fast,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
            "ema_close_base_50": fast,
            "ema_close_base_200": anchor,
            "ema_close_base_500": slow,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(instance_id="ts", min_adx_peak=25.0)
    trace = _trace(df, rule, _ADX_DMI_COLS)
    counters = build_trend_strength_blocker_counters(trace)
    assert REASON_NO_RECENT_PEAK in counters["intrinsic_blocked_reason_breakdown"]
    breakdown = counters["intrinsic_blocked_reason_breakdown"]
    assert sum(breakdown.values()) == counters["intrinsic_blocked_count"]
    assert counters["intrinsic_allowed_count"] + counters["intrinsic_blocked_count"] == len(df)


def test_counters_split_intrinsic_and_final_after_context() -> None:
    n = 10
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    intrinsic = pd.Series(
        [True, False, True, False, True, False, True, False, True, False], index=idx
    )
    final = intrinsic & pd.Series(
        [True, False, False, False, True, False, False, False, True, False],
        index=idx,
    )
    trace = {
        "allowed": intrinsic,
        "blocked_reason": pd.Series(
            ["", REASON_NO_RECENT_PEAK, "", REASON_PEAK_TOO_OLD, "", "", "", "", "", ""],
            index=idx,
        ),
    }
    counters = build_trend_strength_blocker_counters(trace, final_allowed=final)
    assert counters["intrinsic_allowed_count"] == 5
    assert counters["final_allowed_count_after_context"] == 3
    assert counters["allowed_count"] == 3
    assert counters["blocked_count"] == 7


def test_allows_when_ema_stack_wrong_for_side() -> None:
    """EMA direction is owned by direction component; blocker ignores stack."""
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 30.0)
    di_plus = np.full(n, 30.0)
    di_minus = np.full(n, 10.0)
    close = np.linspace(110, 120, n)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(instance_id="ts", min_adx_peak=25.0)
    trace = _trace(df, rule, _ADX_DMI_COLS, side="long")
    assert trace["allowed"].iloc[-1]
    assert "ema_stack_direction_ok" not in trace


def test_short_symmetry_di_on_peak() -> None:
    n = 35
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    adx = np.full(n, 30.0)
    di_plus = np.full(n, 10.0)
    di_minus = np.full(n, 30.0)
    fast = np.linspace(90, 80, n)
    anchor = np.linspace(95, 85, n)
    slow = np.linspace(100, 90, n)
    df = pd.DataFrame(
        {
            "open": fast,
            "high": fast + 1,
            "low": fast - 1,
            "close": fast,
            "volume": 1.0,
            "adx_close_base_14": adx,
            "di_plus_close_base_14": di_plus,
            "di_minus_close_base_14": di_minus,
            "ema_close_base_50": fast,
            "ema_close_base_200": anchor,
            "ema_close_base_500": slow,
        },
        index=idx,
    )
    rule = blocker_trend_strength_episode(instance_id="ts", min_adx_peak=25.0)
    trace = _trace(df, rule, _ADX_DMI_COLS, side="short")
    assert trace["allowed"].iloc[-1]
    assert trace["di_alignment_at_peak"].iloc[-1]
