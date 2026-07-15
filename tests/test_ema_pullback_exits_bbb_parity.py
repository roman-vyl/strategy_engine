from __future__ import annotations

import importlib.util
import math
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from strategy_engine.strategies.ema_pullback.exits import _consecutive_true


def legacy_exit_module():
    for name in (
        "research",
        "research.strategies",
        "research.strategies.ema_pullback",
        "research.strategies.ema_pullback.components",
    ):
        sys.modules.setdefault(name, types.ModuleType(name))
    spec_module = types.ModuleType("research.strategies.ema_pullback.spec")
    spec_module.ExitRuleSpec = object
    spec_module.TradeSide = str
    sys.modules["research.strategies.ema_pullback.spec"] = spec_module
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/components/exits.py"
    )
    module_spec = importlib.util.spec_from_file_location("legacy_exits", path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def assert_series_equal_with_nan(left: pd.Series, right: pd.Series) -> None:
    assert len(left) == len(right)
    for actual, expected in zip(left.tolist(), right.tolist(), strict=True):
        if isinstance(expected, float) and math.isnan(expected):
            assert isinstance(actual, float) and math.isnan(actual)
        else:
            assert actual == expected


def test_signal_exit_primitives_match_legacy_bbb() -> None:
    legacy = legacy_exit_module()
    index = pd.date_range("2024-01-01", periods=7, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "close": [10, 11, 9, 8, 10, 12, 11],
            "rsi": [20, 40, 80, 60, 25, 75, 50],
            "ema": [10, 10, 10, 9, 9, 10, 10],
            "fast": [10, 11, 9, 8, 10, 12, 10],
            "slow": [9, 10, 10, 9, 9, 11, 11],
        },
        index=index,
    )
    rsi_rule = SimpleNamespace(rsi=object(), long_exit_above=70.0, short_exit_below=30.0)
    assert_series_equal_with_nan(
        legacy.rsi_signal_exit(df, side="long", rule=rsi_rule, rsi_col="rsi"),
        (df["rsi"] > 70).fillna(False).astype(bool),
    )
    close_rule = SimpleNamespace(ema=object(), confirm_bars=2)
    expected_close = legacy.ema_close_loss_exit(df, side="long", rule=close_rule, ema_col="ema")
    actual_close = _consecutive_true(df["close"] < df["ema"], 2)
    assert_series_equal_with_nan(actual_close, expected_close)

    cross_rule = SimpleNamespace(fast_ema=object(), confirm_bars=2)
    expected_cross = legacy.ema_cross_loss_exit(
        df,
        side="long",
        rule=cross_rule,
        fast_col="fast",
        slow_col="slow",
    )
    previous_fast = df["fast"].shift(1)
    previous_slow = df["slow"].shift(1)
    cross = ((df["fast"] < df["slow"]) & (previous_fast >= previous_slow)).fillna(False)
    adverse_hold = _consecutive_true(df["fast"] < df["slow"], 2)
    cross_window = cross.astype(int).rolling(2, min_periods=1).max().fillna(0).astype(bool)
    assert_series_equal_with_nan(adverse_hold & cross_window, expected_cross)


def test_distance_exit_primitives_match_legacy_bbb() -> None:
    legacy = legacy_exit_module()
    index = pd.RangeIndex(4)
    df = pd.DataFrame({"distance": [1.0, 2.0, 3.0, 4.0]}, index=index)
    atr_rule = SimpleNamespace(distance=object())
    expected_atr = legacy.atr_distance_exit(df, rule=atr_rule, distance_col="distance")
    pd.testing.assert_series_equal(expected_atr, df["distance"].astype(float))
    usd_rule = SimpleNamespace(usd_distance=12.5)
    expected_usd = legacy.constant_usd_distance_exit(df, rule=usd_rule)
    pd.testing.assert_series_equal(
        expected_usd,
        pd.Series(12.5, index=index, dtype=float),
    )
