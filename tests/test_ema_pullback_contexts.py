from __future__ import annotations

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.validity import Validity
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.contexts import build_context_bundle
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)


def spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "components": {"blockers": []},
        "setups": [],
        "contexts": {
            "htf": {
                "component_id": "htf_context",
                "timeframe": "base",
                "source": "close",
                "fast_period": 2,
                "anchor_period": 3,
                "slow_period": 5,
            }
        },
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
    stream = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 1_200_000)
    return FeatureFrame(
        market=stream,
        requested_range=time_range,
        time_ms=(0, 300_000, 600_000, 900_000),
        series={
            "ema_close_base_2": (None, "3", "1", "2"),
            "ema_close_base_3": (None, "2", "2", "2"),
            "ema_close_base_5": (None, "1", "3", "2"),
        },
        validity={
            key: Validity(None, 0, True, None)
            for key in (
                "ema_close_base_2",
                "ema_close_base_3",
                "ema_close_base_5",
            )
        },
        plan_hash="plan",
        market_data_hash="market",
    )


def test_builds_up_down_neutral_states_on_base_grid() -> None:
    raw_spec = spec()
    plan = build_feature_plan_from_canonical_spec(raw_spec)
    bundle = build_context_bundle(raw_spec, frame(), plan)
    output = bundle.outputs[0]
    assert output.context_ref == "htf"
    assert output.state == ("neutral", "up", "down", "neutral")
    assert output.up == (False, True, False, False)
    assert output.down == (False, False, True, False)
    assert output.neutral == (True, False, False, True)


def test_missing_context_columns_fall_back_to_neutral_like_bbb() -> None:
    raw_spec = spec()
    plan = build_feature_plan_from_canonical_spec(raw_spec)
    missing = frame()
    missing = FeatureFrame(
        market=missing.market,
        requested_range=missing.requested_range,
        time_ms=missing.time_ms,
        series={},
        validity={},
        plan_hash=missing.plan_hash,
        market_data_hash=missing.market_data_hash,
    )
    output = build_context_bundle(raw_spec, missing, plan).outputs[0]
    assert output.state == ("neutral",) * 4
