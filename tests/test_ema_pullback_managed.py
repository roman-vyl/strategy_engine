from __future__ import annotations

from collections import Counter
from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback import managed as managed_module
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
                    },
                    {
                        "rule_id": "ema-cross",
                        "component_id": "ema_cross_loss_exit",
                        "activate_when": {"phase_at_least": "initial_risk"},
                        "exit_kind": "signal",
                        "params": {
                            "confirm_bars": 1,
                            # fast_ema matches the real anchor_stack.fast EMA(2) column
                            # (present in the plan/frame); slow_ema references a period
                            # nothing produces, so plan.ema_columns.get(...) is None and
                            # the runtime check exercises _series()'s missing-output_id
                            # path (all-None tuple) every bar, never triggering.
                            "fast_ema": {"source": "close", "timeframe": "base", "period": 2},
                            "slow_ema": {"source": "close", "timeframe": "base", "period": 999},
                        },
                    },
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


def test_series_materialized_at_most_once_per_output_id_per_replay(monkeypatch) -> None:
    """Regression guard for the managed-replay-series-cache change: _series()
    used to be called from inside the per-bar loop (via _feature_value's ATR
    lookups and _runtime_signal's rsi_signal_exit/ema_cross_loss_exit
    branches), re-materializing the same output_id's full series up to once
    per bar per rule. This spec's stop_management (lock_profit_stop, ATR) and
    runtime_exits (ema_cross_loss_exit, one leg present/ema_close_base_2, one
    leg absent/ema_close_base_999 -- exercising _series()'s missing-output_id
    path too) both read a series on every one of the 6 replay bars, so a
    regression back to per-bar re-materialization would push these counts
    well above 1."""

    call_counts: Counter[str] = Counter()
    original_series = managed_module._series

    def counting_series(frame: FeatureFrame, output_id: str) -> tuple[float | None, ...]:
        call_counts[output_id] += 1
        return original_series(frame, output_id)

    monkeypatch.setattr(managed_module, "_series", counting_series)

    raw = spec()
    feature_frame, plan = frame(raw)
    evaluate_managed_replay(
        raw,
        feature_frame,
        plan,
        trade_id="L1",
        side="long",
        entry_time_ms=0,
        entry_price=100.0,
    )

    assert call_counts["atr_close_base_2"] == 1
    assert call_counts["ema_close_base_2"] == 1
    # ema_close_base_999 is planned (referenced by the ema-cross runtime rule)
    # but absent from this test's hand-built FeatureFrame.series -- exercising
    # _series()'s missing-output_id path (all-None tuple), which the cache
    # must memoize like any other result, not bypass.
    assert call_counts["ema_close_base_999"] == 1
    assert set(call_counts) == {"atr_close_base_2", "ema_close_base_2", "ema_close_base_999"}


def test_series_missing_output_id_returns_none_tuple_matching_frame_length() -> None:
    """Direct confirmation that the cache does not change _series()'s
    documented missing-output_id behavior: an all-None tuple the length of
    frame.time_ms, not an exception and not a bypassed/empty result."""

    raw = spec()
    feature_frame, _plan = frame(raw)
    result = managed_module._series(feature_frame, "does-not-exist")
    assert len(result) == len(feature_frame.time_ms)
    assert all(value is None for value in result)
