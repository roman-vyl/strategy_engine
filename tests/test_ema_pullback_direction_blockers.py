from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.context_consumption import ContextConsumptionRecord
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)


def frame() -> FeatureFrame:
    market = MarketStream("BTCUSDT.P", "5m")
    return FeatureFrame(
        market=market,
        requested_range=TimeRange(0, 1_200_000),
        time_ms=(0, 300_000, 600_000, 900_000),
        series={
            "ema_close_base_2": ("3", "2", "1", "4"),
            "ema_close_base_3": ("2", "2", "2", "3"),
            "ema_close_base_5": ("1", "2", "3", "2"),
            "rsi_close_base_3": ("50", "85", "50", "50"),
        },
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=tuple(
            MarketBar(t, Decimal(o), Decimal("5"), Decimal("0"), Decimal(c), Decimal("1"))
            for t, o, c in zip(
                (0, 300_000, 600_000, 900_000),
                ("1", "2", "3", "4"),
                ("2", "1", "3", "5"),
                strict=True,
            )
        ),
    )


def spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [
                {"instance_id": "candle", "component_id": "counter_candle_blocker"},
                {
                    "instance_id": "rsi",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "rsi": {"timeframe": "base", "period": 3},
                    "lookback": 2,
                    "long_block_above": 80,
                    "short_block_below": 20,
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


def test_direction_and_multiple_blockers_are_composed_per_side() -> None:
    planned = build_feature_plan_from_canonical_spec(spec())
    output = evaluate_direction_and_blockers(spec(), frame(), planned, ())
    long, short = output
    assert long.direction.allowed == (True, False, False, True)
    assert long.blockers[0].allowed == (True, False, True, True)
    assert long.blockers[1].allowed == (True, False, False, True)
    assert long.blockers_ok == (True, False, False, True)
    assert long.pre_setup_allowed == (True, False, False, True)
    assert short.direction.allowed == (False, False, True, False)


def test_context_gate_is_applied_after_intrinsic_blocker() -> None:
    raw = spec()
    blockers = raw["components"]["blockers"]  # type: ignore[index]
    blockers[0]["context_consumption"] = {  # type: ignore[index]
        "context_ref": "htf",
        "policy": {"policy_id": "htf_regime_gate", "params": {"allowed_regimes": ["aligned"]}},
    }
    planned = build_feature_plan_from_canonical_spec(raw)
    record = ContextConsumptionRecord(
        role="blocker",
        context_ref="htf",
        policy_id="htf_regime_gate",
        side="long",
        component_id="counter_candle_blocker",
        instance_id="candle",
        raw_state=("up", "down", "up", "down"),
        allowed=(True, False, True, False),
        allowed_regimes=("aligned",),
    )
    output = evaluate_direction_and_blockers(raw, frame(), planned, (record,))
    assert output[0].blockers[0].intrinsic_allowed == (True, False, True, True)
    assert output[0].blockers[0].allowed == (True, False, True, False)
