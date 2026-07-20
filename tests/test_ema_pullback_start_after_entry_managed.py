from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.managed import (
    evaluate_start_after_entry_managed_projection,
)


def _spec(*, stop_buffer: float = 0.0, take_action: str = "keep_initial") -> dict[str, object]:
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
                            "params": {"threshold": 0.05},
                        },
                    },
                ],
                "stop_management": [
                    {
                        "rule_id": "be",
                        "component_id": "break_even_stop",
                        "activate_when": {"phase_at_least": "protected"},
                        "params": {"buffer_type": "none", "buffer": stop_buffer},
                    }
                ],
                "take_management": [
                    {
                        "rule_id": "take",
                        "component_id": "take_profile_switch",
                        "activate_when": {"phase_at_least": "protected"},
                        "params": {"action": take_action},
                    }
                ],
                "runtime_exits": [],
            },
        },
    }


def _frame(raw: dict[str, object]) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(raw)
    times = (0, 300_000, 600_000)
    bars = (
        MarketBar(0, Decimal("100"), Decimal("160"), Decimal("40"), Decimal("100"), Decimal("1")),
        MarketBar(
            300_000,
            Decimal("101"),
            Decimal("106"),
            Decimal("98"),
            Decimal("104"),
            Decimal("1"),
        ),
        MarketBar(
            600_000,
            Decimal("104"),
            Decimal("108"),
            Decimal("103"),
            Decimal("107"),
            Decimal("1"),
        ),
    )
    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, 900_000),
            times,
            {},
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


def _project(
    *,
    target_time_ms: int,
    planned_entry_price: float = 100.0,
    initial_stop_price: float = 95.0,
    initial_take_price: float = 120.0,
    stop_buffer: float = 0.0,
    take_action: str = "keep_initial",
):
    raw = _spec(stop_buffer=stop_buffer, take_action=take_action)
    frame, plan = _frame(raw)
    return evaluate_start_after_entry_managed_projection(
        raw,
        frame,
        plan,
        trade_id="T1",
        side="long",
        entry_time_ms=0,
        planned_entry_price=planned_entry_price,
        initial_stop_price=initial_stop_price,
        initial_take_price=initial_take_price,
        target_time_ms=target_time_ms,
    )


def test_entry_target_keeps_initial_state_and_excludes_entry_ohlc() -> None:
    result = _project(target_time_ms=0)

    assert result.replay.events == ()
    assert result.replay.bars == ()
    assert result.replay.final_state.phase == "initial_risk"
    assert result.replay.final_state.bars_in_trade == 1
    assert result.replay.final_state.mfe_pct == 0.0
    assert result.replay.final_state.mae_pct == 0.0
    assert result.desired_stop_price == 95.0
    assert result.desired_take_price == 120.0


def test_first_post_entry_bar_has_two_bars_and_uses_only_post_entry_ohlc() -> None:
    result = _project(target_time_ms=300_000)

    assert len(result.replay.bars) == 1
    decision = result.replay.bars[0]
    assert decision.bar_index == 1
    assert decision.bars_in_trade == 2
    assert decision.mfe_pct == 0.06
    assert decision.mae_pct == 0.02
    assert result.replay.final_state.phase == "runner"


def test_planned_price_is_the_entry_relative_basis() -> None:
    result = _project(target_time_ms=300_000, planned_entry_price=102.0)

    assert result.replay.final_state.entry_price == 102.0
    assert result.replay.final_state.mfe_pct == (106.0 - 102.0) / 102.0
    assert result.replay.final_state.mae_pct == (102.0 - 98.0) / 102.0
    assert result.desired_stop_price == 102.0


def test_seeded_stop_is_tighten_only() -> None:
    looser_candidate = _project(
        target_time_ms=300_000,
        initial_stop_price=101.0,
        stop_buffer=0.0,
    )
    tighter_candidate = _project(
        target_time_ms=300_000,
        initial_stop_price=95.0,
        stop_buffer=1.0,
    )

    assert looser_candidate.desired_stop_price == 101.0
    assert not any(
        event.event_type == "active_stop_updated" for event in looser_candidate.replay.events
    )
    assert tighter_candidate.desired_stop_price == 101.0
    assert any(
        event.event_type == "active_stop_updated" for event in tighter_candidate.replay.events
    )


def test_initial_take_can_be_disabled_by_managed_take_profile() -> None:
    result = _project(target_time_ms=300_000, take_action="disable_fixed_tp")

    assert result.replay.final_state.active_take_profile == "disable_initial_tp"
    assert result.desired_take_price is None
