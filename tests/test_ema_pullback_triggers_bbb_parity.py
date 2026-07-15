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
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation
from strategy_engine.strategies.ema_pullback.triggers import evaluate_triggers


def legacy_trigger_module():
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
        / "legacy_source/bbb/research/strategies/ema_pullback/components/triggers.py"
    )
    module_spec = importlib.util.spec_from_file_location("legacy_triggers", path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def assert_trace_matches(actual: tuple[object, ...], expected: pd.Series) -> None:
    for left, right in zip(actual, expected.tolist(), strict=True):
        if isinstance(right, float) and math.isnan(right):
            assert isinstance(left, float) and math.isnan(left)
        else:
            assert left == right


def test_all_trigger_components_match_legacy_bbb() -> None:
    legacy = legacy_trigger_module()
    index = pd.date_range("2024-01-01", periods=8, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [11, 10, 9, 11, 12, 10, 9, 11],
            "high": [12, 11, 10.5, 12, 13, 11, 10, 12],
            "low": [10.5, 9, 8, 10.5, 11, 9, 8, 10],
            "close": [11, 10.5, 9, 11, 12, 9.5, 9, 11],
            "ema_close_base_2": [11] * 8,
            "ema_close_base_3": [10] * 8,
            "ema_close_base_5": [9] * 8,
        },
        index=index,
    )
    base = {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [{"instance_id": "none", "component_id": "no_blockers"}],
        },
        "setups": [],
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
    time_ms = tuple(i * 300_000 for i in range(len(df)))
    frame = FeatureFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(0, len(df) * 300_000),
        time_ms,
        {
            name: tuple(str(value) for value in df[name])
            for name in (
                "ema_close_base_2",
                "ema_close_base_3",
                "ema_close_base_5",
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
    setup_allowed = tuple(True for _ in time_ms)
    setup_inputs = (
        SideSetupEvaluation("long", (), setup_allowed, setup_allowed),
        SideSetupEvaluation("short", (), setup_allowed, setup_allowed),
    )
    cases = (
        ("reclaim_anchor", 2, legacy.reclaim_anchor_trace),
        ("strong_reclaim_anchor", 2, legacy.strong_reclaim_anchor_trace),
        ("touch_anchor", None, legacy.touch_anchor_trace),
    )
    for component_id, lookback, legacy_fn in cases:
        spec = dict(base)
        components = dict(base["components"])
        trigger = {"component_id": component_id}
        if lookback is not None:
            trigger["lookback"] = lookback
        components["trigger"] = trigger
        spec["components"] = components
        plan = build_feature_plan_from_canonical_spec(spec)
        actual = evaluate_triggers(spec, frame, plan, setup_inputs)
        for result in actual:
            if lookback is None:
                expected = legacy_fn(df, "ema_close_base_3", side=result.side)
            else:
                expected = legacy_fn(
                    df,
                    "ema_close_base_3",
                    lookback,
                    side=result.side,
                )
            assert result.trigger.allowed == tuple(expected["trigger"].astype(bool))
            for key, values in result.trigger.trace.items():
                assert_trace_matches(values, expected[key])
