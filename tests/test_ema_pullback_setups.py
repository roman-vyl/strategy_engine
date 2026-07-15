from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
)
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.setups import evaluate_setups


def raw_spec() -> dict[str, object]:
    return {
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


def feature_frame() -> FeatureFrame:
    time_ms = tuple(index * 300_000 for index in range(7))
    opens = ("5", "6", "7", "8", "9", "8", "10")
    closes = ("6", "7", "8", "9", "8", "10", "11")
    lows = ("4", "5", "6", "6.5", "7", "7", "9")
    highs = ("7", "8", "9", "10", "10", "11", "12")
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
        requested_range=TimeRange(0, len(time_ms) * 300_000),
        time_ms=time_ms,
        series={
            "ema_close_base_2": ("6", "7", "8", "9", "9", "10", "11"),
            "ema_close_base_3": ("5", "6", "7", "8", "8", "9", "10"),
            "ema_close_base_5": ("4", "5", "6", "7", "7", "8", "9"),
            "atr_close_base_2": (None, "1", "1", "1", "1", "1", "1"),
        },
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=bars,
    )


def test_setups_are_and_composed_after_direction_and_blockers() -> None:
    spec = raw_spec()
    frame = feature_frame()
    plan = build_feature_plan_from_canonical_spec(spec)
    prior = evaluate_direction_and_blockers(spec, frame, plan, ())
    output = evaluate_setups(spec, frame, plan, (), prior)[0]
    assert [item.component_id for item in output.setups] == [
        "untouched_anchor_setup",
        "ema_bounce_counter_setup",
        "anchor_stack_width_setup",
    ]
    assert output.setups_ok == tuple(
        all(item.final_setup_allowed[index] for item in output.setups)
        for index in range(len(frame.time_ms))
    )
    assert output.pre_trigger_allowed == tuple(
        left and right
        for left, right in zip(prior[0].pre_setup_allowed, output.setups_ok, strict=True)
    )


def test_setup_context_gate_is_applied_after_local_semantics() -> None:
    spec = raw_spec()
    setup = spec["setups"][0]  # type: ignore[index]
    setup["context_consumption"] = {  # type: ignore[index]
        "context_ref": "htf",
        "policy": {
            "policy_id": "htf_regime_gate",
            "params": {"allowed_regimes": ["aligned"]},
        },
    }
    frame = feature_frame()
    plan = build_feature_plan_from_canonical_spec(spec)
    prior = evaluate_direction_and_blockers(spec, frame, plan, ())
    gate = (True, False, True, False, True, False, True)
    record = ContextConsumptionRecord(
        role="setup",
        context_ref="htf",
        policy_id="htf_regime_gate",
        side="long",
        component_id="untouched_anchor_setup",
        instance_id="untouched",
        raw_state=("up",) * len(gate),
        allowed=gate,
        allowed_regimes=("aligned",),
    )
    result = evaluate_setups(spec, frame, plan, (record,), prior)[0].setups[0]
    assert result.final_setup_allowed == tuple(
        left and right for left, right in zip(result.local_setup_allowed, gate, strict=True)
    )
