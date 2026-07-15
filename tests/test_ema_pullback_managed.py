from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.managed import evaluate_managed_replay


def spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long"]},
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
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
            "exit_management": {
                "mode": "managed",
                "phase_rules": [
                    {
                        "rule_id": "to-protected",
                        "to_phase": "protected",
                        "condition": {
                            "component_id": "bars_in_trade",
                            "params": {"threshold": 2},
                        },
                    },
                    {
                        "rule_id": "to-runner",
                        "to_phase": "runner",
                        "condition": {
                            "component_id": "mfe_pct",
                            "params": {"threshold": 0.04},
                        },
                    },
                    {
                        "rule_id": "to-exhaustion",
                        "to_phase": "exhaustion",
                        "condition": {
                            "component_id": "bars_in_trade",
                            "params": {"threshold": 5},
                        },
                    },
                ],
                "stop_management": [
                    {
                        "rule_id": "be",
                        "component_id": "break_even_stop",
                        "activate_when": {"phase_at_least": "protected"},
                        "params": {"buffer_type": "none", "buffer": 0.25},
                    },
                    {
                        "rule_id": "lock",
                        "component_id": "lock_profit_stop",
                        "activate_when": {"phase_at_least": "runner"},
                        "params": {"lock_atr": 0.5, "atr_period": 2},
                    },
                ],
                "take_management": [
                    {
                        "rule_id": "disable-tp",
                        "component_id": "take_profile_switch",
                        "activate_when": {"phase_at_least": "runner"},
                        "params": {"action": "disable_initial_tp"},
                    }
                ],
                "runtime_exits": [
                    {
                        "rule_id": "close-exhaustion",
                        "component_id": "phase_runtime_exit",
                        "activate_when": {"phase_at_least": "exhaustion"},
                        "exit_kind": "market_close",
                        "params": {"exit_price": "close"},
                    }
                ],
            },
        },
    }


def frame(raw: dict[str, object]) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(raw)
    times = tuple(i * 300_000 for i in range(6))
    bars = tuple(
        MarketBar(
            times[i],
            Decimal(str(100 + i)),
            Decimal(str(102 + i)),
            Decimal(str(99 + i)),
            Decimal(str(101 + i)),
            Decimal("1"),
        )
        for i in range(6)
    )
    atr_id = next(
        feature.output_id
        for feature in plan.indicator_plan.features
        if feature.kind == "atr"
        and feature.timeframe == "base"
        and feature.parameters.get("period") == 2
    )
    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, 1_800_000),
            times,
            {atr_id: (None, "2", "2", "2", "2", "2")},
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


def test_managed_replay_emits_phase_stop_take_and_runtime_decisions() -> None:
    raw = spec()
    feature_frame, plan = frame(raw)
    result = evaluate_managed_replay(
        raw,
        feature_frame,
        plan,
        trade_id="L1",
        side="long",
        entry_time_ms=0,
        entry_price=100.0,
    )
    types = [event.event_type for event in result.events]
    assert "phase_changed" in types
    assert "active_stop_updated" in types
    assert "active_take_updated" in types
    assert "runtime_exit_triggered" in types
    assert result.final_state.phase == "exhaustion"
    assert result.final_state.active_stop_price == 101.0
    assert result.final_state.active_take_profile == "disable_initial_tp"
    assert result.final_state.active_runtime_exit_rules == ("close-exhaustion",)


def test_managed_decisions_are_effective_from_next_bar() -> None:
    raw = spec()
    feature_frame, plan = frame(raw)
    result = evaluate_managed_replay(
        raw,
        feature_frame,
        plan,
        trade_id="L1",
        side="long",
        entry_time_ms=0,
        entry_price=100.0,
    )
    managed = [event for event in result.events if event.event_type != "phase_changed"]
    assert managed
    assert all(event.metadata["effective_from_bar"] == event.bar_index + 1 for event in managed)
