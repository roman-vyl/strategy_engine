from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation
from strategy_engine.strategies.ema_pullback.triggers import evaluate_triggers


def raw_spec(component_id: str, lookback: int = 1) -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [{"instance_id": "none", "component_id": "no_blockers"}],
            "trigger": {"component_id": component_id, "lookback": lookback},
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


def frame() -> FeatureFrame:
    time_ms = tuple(index * 300_000 for index in range(6))
    opens = ("11", "9", "11", "11", "9", "9")
    highs = ("12", "11", "12", "12", "11", "11")
    lows = ("10", "8", "10", "10", "8", "8")
    closes = ("11", "9", "11", "11", "9", "9")
    bars = tuple(
        MarketBar(
            timestamp,
            Decimal(open_value),
            Decimal(high_value),
            Decimal(low_value),
            Decimal(close_value),
            Decimal("1"),
        )
        for timestamp, open_value, high_value, low_value, close_value in zip(
            time_ms, opens, highs, lows, closes, strict=True
        )
    )
    return FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, 1_800_000),
        time_ms=time_ms,
        series={
            "ema_close_base_2": ("11",) * 6,
            "ema_close_base_3": ("10",) * 6,
            "ema_close_base_5": ("9",) * 6,
        },
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=bars,
    )


def setup_inputs(length: int) -> tuple[SideSetupEvaluation, ...]:
    allowed = tuple(True for _ in range(length))
    return (
        SideSetupEvaluation("long", (), allowed, allowed),
        SideSetupEvaluation("short", (), allowed, allowed),
    )


def test_reclaim_anchor_uses_prior_wick_probe_not_current_probe() -> None:
    spec = raw_spec("reclaim_anchor", lookback=1)
    output = evaluate_triggers(
        spec,
        frame(),
        build_feature_plan_from_canonical_spec(spec),
        setup_inputs(6),
    )
    assert output[0].trigger.allowed == (False, False, True, True, False, False)
    assert output[1].trigger.allowed == (False, True, False, False, True, True)


def test_strong_reclaim_requires_prior_close_probe() -> None:
    spec = raw_spec("strong_reclaim_anchor", lookback=1)
    output = evaluate_triggers(
        spec,
        frame(),
        build_feature_plan_from_canonical_spec(spec),
        setup_inputs(6),
    )
    assert output[0].trigger.allowed == (False, False, True, False, False, False)
    assert output[1].trigger.allowed == (False, True, False, False, True, False)


def test_touch_anchor_is_current_bar_side_aware() -> None:
    spec = raw_spec("touch_anchor")
    output = evaluate_triggers(
        spec,
        frame(),
        build_feature_plan_from_canonical_spec(spec),
        setup_inputs(6),
    )
    assert output[0].trigger.allowed == (True, False, True, True, False, False)
    assert output[1].trigger.allowed == (False, True, False, False, True, True)


def test_pre_risk_combines_setup_and_trigger() -> None:
    spec = raw_spec("touch_anchor")
    allowed = (True, False, True, False, True, False)
    setups = (SideSetupEvaluation("long", (), allowed, allowed),)
    result = evaluate_triggers(
        spec,
        frame(),
        build_feature_plan_from_canonical_spec(spec),
        setups,
    )[0]
    assert result.pre_risk_entry_allowed == (True, False, True, False, False, False)
