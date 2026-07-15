from __future__ import annotations

import importlib.util
import math
import sys
import types
from decimal import Decimal
from pathlib import Path

import pandas as pd

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.setups import evaluate_setups


def legacy_setup_module():
    for name in (
        "research",
        "research.strategies",
        "research.strategies.ema_pullback",
        "research.strategies.ema_pullback.components",
    ):
        sys.modules.setdefault(name, types.ModuleType(name))
    spec_module = types.ModuleType("research.strategies.ema_pullback.spec")
    spec_module.TradeSide = str
    sys.modules["research.strategies.ema_pullback.spec"] = spec_module
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/components/setup.py"
    )
    module_spec = importlib.util.spec_from_file_location("legacy_setup", path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def assert_series_matches(actual: tuple[object, ...], expected: pd.Series) -> None:
    assert len(actual) == len(expected)
    for left, right in zip(actual, expected.tolist(), strict=True):
        if isinstance(right, float) and math.isnan(right):
            assert isinstance(left, float) and math.isnan(left)
        else:
            assert left == right


def test_all_setup_components_match_legacy_bbb() -> None:
    legacy = legacy_setup_module()
    index = pd.date_range("2024-01-01", periods=9, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [5, 6, 7, 8, 9, 8, 10, 11, 10],
            "high": [7, 8, 9, 10, 10, 11, 12, 13, 12],
            "low": [4, 5, 6, 6.5, 7, 7, 9, 9.5, 9],
            "close": [6, 7, 8, 9, 8, 10, 11, 10, 11],
            "ema_close_base_2": [6, 7, 8, 9, 9, 10, 11, 11, 11],
            "ema_close_base_3": [5, 6, 7, 8, 8, 9, 10, 10, 10],
            "ema_close_base_5": [4, 5, 6, 7, 7, 8, 9, 9, 9],
            "atr_close_base_2": [None, 1, 1, 1, 1, 1, 1, 1, 1],
        },
        index=index,
    )
    raw = {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long"]},
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [{"instance_id": "none", "component_id": "no_blockers"}],
        },
        "setups": [
            {
                "instance_id": "untouched",
                "component_id": "untouched_anchor_setup",
                "params": {"lookback": 2, "active_bars": 2},
            },
            {
                "instance_id": "bounce",
                "component_id": "ema_bounce_counter_setup",
                "params": {
                    "max_bounces": 2,
                    "raw_touch_mode": "range_cross",
                    "touch_lookback_bars": 2,
                    "trend_start_confirmation_bars": 1,
                    "trend_break_confirmation_bars": 1,
                },
            },
            {
                "instance_id": "width",
                "component_id": "anchor_stack_width_setup",
                "params": {
                    "atr_timeframe": "base",
                    "atr_period": 2,
                    "min_current_width_atr": 1.0,
                    "min_recent_width_atr": 1.0,
                    "width_lookback_bars": 2,
                },
            },
        ],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }
    plan = build_feature_plan_from_canonical_spec(raw)
    time_ms = tuple(i * 300_000 for i in range(len(df)))
    frame = FeatureFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(0, len(df) * 300_000),
        time_ms,
        {
            column: tuple(None if pd.isna(value) else str(value) for value in df[column])
            for column in (
                "ema_close_base_2",
                "ema_close_base_3",
                "ema_close_base_5",
                "atr_close_base_2",
            )
        },
        {},
        "plan",
        "market",
        tuple(
            MarketBar(
                time_ms[i],
                Decimal(str(df.open.iloc[i])),
                Decimal(str(df.high.iloc[i])),
                Decimal(str(df.low.iloc[i])),
                Decimal(str(df.close.iloc[i])),
                Decimal("1"),
            )
            for i in range(len(df))
        ),
    )
    prior = evaluate_direction_and_blockers(raw, frame, plan, ())
    actual = evaluate_setups(raw, frame, plan, (), prior)[0]

    expected_untouched = legacy.untouched_anchor_setup_trace(
        df, "ema_close_base_3", 2, 2, side="long"
    )
    expected_bounce = legacy.ema_bounce_counter_setup_trace(
        df,
        "ema_close_base_2",
        "ema_close_base_3",
        "ema_close_base_5",
        max_bounces=2,
        raw_touch_mode="range_cross",
        touch_lookback_bars=2,
        trend_start_confirmation_bars=1,
        trend_break_confirmation_bars=1,
        side="long",
    )
    expected_width = legacy.anchor_stack_width_setup_trace(
        df,
        "ema_close_base_2",
        "ema_close_base_3",
        "ema_close_base_5",
        "atr_close_base_2",
        min_current_width_atr=1.0,
        min_recent_width_atr=1.0,
        width_lookback_bars=2,
        side="long",
    )
    expected = (expected_untouched, expected_bounce, expected_width)
    for mask, trace in zip(actual.setups, expected, strict=True):
        assert mask.local_setup_allowed == tuple(trace["setup"].astype(bool))
        for key, values in mask.trace.items():
            assert_series_matches(values, trace[key])
