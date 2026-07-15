from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.exits import evaluate_exit_policy
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)


def raw_spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "sl",
                            "component_id": "atr_stop_loss",
                            "exit_kind": "stop_loss",
                            "distance": {"timeframe": "base", "period": 2, "multiplier": 1.5},
                        },
                        {
                            "instance_id": "tp",
                            "component_id": "constant_usd_take_profit",
                            "exit_kind": "take_profit",
                            "usd_distance": 4.0,
                        },
                        {
                            "instance_id": "rsi",
                            "component_id": "rsi_signal_exit",
                            "exit_kind": "signal",
                            "rsi": {"timeframe": "base", "period": 2},
                            "long_exit_above": 70.0,
                            "short_exit_below": 30.0,
                        },
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def frame(spec: dict[str, object]) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(spec)
    times = tuple(i * 300_000 for i in range(4))
    bars = tuple(
        MarketBar(
            times[i],
            Decimal(str(100 + i)),
            Decimal(str(102 + i)),
            Decimal(str(99 + i)),
            Decimal(str(100 + i)),
            Decimal("1"),
        )
        for i in range(4)
    )
    series: dict[str, tuple[str | None, ...]] = {
        plan.anchor_columns["fast"]: ("101", "102", "103", "104"),
        plan.anchor_columns["anchor"]: ("100", "101", "102", "103"),
        plan.anchor_columns["slow"]: ("99", "100", "101", "102"),
        plan.rsi_columns[("base", 2)]: (None, "20", "80", "50"),
    }
    if "sl" in plan.exit_distance_columns:
        series[plan.exit_distance_columns["sl"]] = (None, "1.5", "3", "4.5")
    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, 1_200_000),
            times,
            series,
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


def test_exit_policy_returns_signal_and_distance_outputs() -> None:
    spec = raw_spec()
    feature_frame, plan = frame(spec)
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    assert result.signal_exit_long == (False, False, True, False)
    assert result.signal_exit_short == (False, True, False, False)
    assert result.stop_loss_ratio_long[0] is None
    assert result.stop_loss_ratio_long[1] == pytest.approx(1.5 / 101)
    assert result.take_profit_ratio_long[0] == pytest.approx(4 / 100)
    assert result.stop_ready_long == (False, True, True, True)


def test_unknown_exit_component_is_rejected() -> None:
    spec = raw_spec()
    policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    policy["always_on"]["exits"][0]["component_id"] = "future_exit"  # type: ignore[index]
    feature_frame, plan = frame(spec)
    with pytest.raises(InvalidRequestError, match="unsupported exit component"):
        evaluate_exit_policy(spec, feature_frame, plan, ())


def test_profile_selection_uses_side_relative_context_result() -> None:
    from strategy_engine.strategies.ema_pullback.context_consumption import (
        ContextConsumptionRecord,
    )

    spec = raw_spec()
    policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    policy["always_on"]["exits"] = []  # type: ignore[index]
    policy["profiles"]["aligned"]["exits"] = [  # type: ignore[index]
        {
            "instance_id": "aligned-rsi",
            "component_id": "rsi_signal_exit",
            "exit_kind": "signal",
            "rsi": {"timeframe": "base", "period": 2},
            "long_exit_above": 70.0,
            "short_exit_below": 30.0,
        }
    ]
    feature_frame, plan = frame(spec)
    consumption = (
        ContextConsumptionRecord(
            role="exit_policy",
            context_ref="htf",
            policy_id="exit_profile_by_htf_state",
            side=None,
            component_id="exit_policy",
            instance_id=None,
            raw_state=("up", "down", "up", "down"),
            profile_long=("aligned", "countertrend", "aligned", "countertrend"),
            profile_short=("countertrend", "aligned", "countertrend", "aligned"),
        ),
    )
    result = evaluate_exit_policy(spec, feature_frame, plan, consumption)
    assert result.signal_exit_long == (False, False, True, False)
    assert result.signal_exit_short == (False, True, False, False)
