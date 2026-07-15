from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)


@dataclass(frozen=True)
class RsiFeatureSpec:
    timeframe: str = "base"
    period: int = 3


@dataclass(frozen=True)
class TrendStrengthEpisodeBlockerParams:
    timeframe: str = "base"
    adx_period: int = 3
    min_adx_peak: float = 25.0
    peak_lookback_bars: int = 5
    max_bars_since_peak: int = 3
    min_current_adx: float = 15.0
    require_di_alignment_on_peak: bool = True
    block_on_opposite_di_flip: bool = True
    opposite_di_margin: float = 0.0


@dataclass(frozen=True)
class BlockerRuleSpec:
    instance_id: str
    component_id: str
    rsi: RsiFeatureSpec | None = None
    lookback: int = 3
    long_block_above: float | None = 80.0
    short_block_below: float | None = 20.0
    trend_strength: TrendStrengthEpisodeBlockerParams | None = None


def legacy_modules():
    for name in [
        "research",
        "research.strategies",
        "research.strategies.ema_pullback",
        "research.strategies.ema_pullback.components",
    ]:
        sys.modules.setdefault(name, types.ModuleType(name))
    spec_module = types.ModuleType("research.strategies.ema_pullback.spec")
    spec_module.TradeSide = str
    spec_module.BlockerRuleSpec = BlockerRuleSpec
    spec_module.TrendStrengthEpisodeBlockerParams = TrendStrengthEpisodeBlockerParams
    sys.modules["research.strategies.ema_pullback.spec"] = spec_module
    root = (
        Path(__file__).parents[1] / "legacy_source/bbb/research/strategies/ema_pullback/components"
    )
    loaded = {}
    for name in ("trend_strength_episode", "direction", "blockers"):
        full = f"research.strategies.ema_pullback.components.{name}"
        module_spec = importlib.util.spec_from_file_location(full, root / f"{name}.py")
        assert module_spec and module_spec.loader
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[full] = module
        module_spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


def test_direction_counter_rsi_and_trend_strength_match_legacy() -> None:
    legacy = legacy_modules()
    index = pd.date_range("2024-01-01", periods=6, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6],
            "close": [2, 1, 3, 5, 4, 7],
            "ema_close_base_2": [3, 2, 1, 4, 5, 6],
            "ema_close_base_3": [2, 2, 2, 3, 4, 5],
            "ema_close_base_5": [1, 2, 3, 2, 3, 4],
            "rsi_close_base_3": [50, 85, 50, 50, 10, 50],
            "adx_close_base_3": [None, None, 30, 28, 20, 18],
            "di_plus_close_base_3": [None, None, 35, 30, 25, 10],
            "di_minus_close_base_3": [None, None, 10, 12, 15, 30],
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
            "blockers": [
                {"instance_id": "counter", "component_id": "counter_candle_blocker"},
                {
                    "instance_id": "rsi",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "rsi": {"timeframe": "base", "period": 3},
                    "lookback": 3,
                    "long_block_above": 80,
                    "short_block_below": 20,
                },
                {
                    "instance_id": "trend",
                    "component_id": "trend_strength_episode_blocker",
                    "trend_strength": {
                        "timeframe": "base",
                        "adx_period": 3,
                        "min_adx_peak": 25,
                        "peak_lookback_bars": 5,
                        "max_bars_since_peak": 3,
                        "min_current_adx": 15,
                        "require_di_alignment_on_peak": True,
                        "block_on_opposite_di_flip": True,
                        "opposite_di_margin": 0,
                    },
                },
            ],
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
    plan = build_feature_plan_from_canonical_spec(raw)
    from decimal import Decimal

    from strategy_engine.domain.market import MarketBar

    frame = FeatureFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(0, 1_800_000),
        tuple(i * 300_000 for i in range(6)),
        {
            c: tuple(None if pd.isna(v) else str(v) for v in df[c])
            for c in df.columns
            if c not in {"open", "close"}
        },
        {},
        "p",
        "m",
        tuple(
            MarketBar(
                i * 300_000,
                Decimal(str(df.open.iloc[i])),
                Decimal("10"),
                Decimal("0"),
                Decimal(str(df.close.iloc[i])),
                Decimal("1"),
            )
            for i in range(6)
        ),
    )
    actual = evaluate_direction_and_blockers(raw, frame, plan, ())[0]
    assert actual.direction.allowed == tuple(
        legacy["direction"].ema_anchor_stack_trend(
            df, "ema_close_base_2", "ema_close_base_3", "ema_close_base_5", side="long"
        )
    )
    counter_rule = actual.blockers[0]
    assert counter_rule.allowed == tuple(legacy["blockers"].counter_candle_blocker(df, side="long"))
    rsi_rule = BlockerRuleSpec("rsi", "rsi_lookback_extreme_blocker", RsiFeatureSpec(), 3, 80, 20)
    assert actual.blockers[1].allowed == tuple(
        legacy["blockers"].rsi_lookback_extreme_blocker(
            df, side="long", rule=rsi_rule, rsi_col="rsi_close_base_3"
        )
    )
    trend_rule = BlockerRuleSpec(
        "trend",
        "trend_strength_episode_blocker",
        trend_strength=TrendStrengthEpisodeBlockerParams(),
    )
    expected_trend = legacy["trend_strength_episode"].trend_strength_episode_blocker_trace(
        df,
        side="long",
        rule=trend_rule,
        adx_col="adx_close_base_3",
        di_plus_col="di_plus_close_base_3",
        di_minus_col="di_minus_close_base_3",
    )
    assert actual.blockers[2].allowed == tuple(expected_trend["allowed"])
    assert actual.blockers[2].trace["blocked_reason"] == tuple(expected_trend["blocked_reason"])
