"""Initial-R lock and true trailing stop managed-policy semantics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from test_ema_pullback_managed import spec

from strategy_engine.adapters.http.strategy_serialization import _serialize_rule
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.contracts import ManagedStopActionRule
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.historical_managed_projection import (
    build_historical_managed_projection,
)
from strategy_engine.strategies.ema_pullback.managed import evaluate_managed_replay

STEP = 300_000


def _spec(*, legacy_distance: float | None = None) -> dict[str, Any]:
    raw = spec()
    management: Any = raw["trade_management"]
    config = management["exit_management"]
    config["phase_rules"] = []
    config["take_management"] = []
    config["runtime_exits"] = []
    rules: list[dict[str, object]] = []
    if legacy_distance is not None:
        rules.append(
            {
                "rule_id": "legacy",
                "component_id": "break_even_stop",
                "activate_when": {"phase_at_least": "initial_risk"},
                "params": {"buffer_type": "none", "buffer": legacy_distance},
            }
        )
    rules.extend(
        [
            {
                "rule_id": "lock",
                "component_id": "initial_r_lock_stop",
                "activate_when": {"phase_at_least": "initial_risk"},
                "params": {"trigger_r": 6, "lock_r": 4},
            },
            {
                "rule_id": "trail",
                "component_id": "initial_r_trailing_stop",
                "activate_when": {"phase_at_least": "initial_risk"},
                "params": {"trigger_r": 6, "trail_distance_r": 2},
            },
        ]
    )
    config["stop_management"] = rules
    return raw


def _frame(raw: dict[str, Any], side: str) -> tuple[FeatureFrame, object]:
    moves = [10, 12, 14, 16, 23, 20, 20]
    times = tuple(index * STEP for index in range(len(moves)))
    bars = tuple(
        MarketBar(
            times[index],
            Decimal("100"),
            Decimal(str(100 + move)) if side == "long" else Decimal("100"),
            Decimal("100") if side == "long" else Decimal(str(100 - move)),
            Decimal("100"),
            Decimal("1"),
        )
        for index, move in enumerate(moves)
    )
    plan = build_feature_plan_from_canonical_spec(raw)
    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, len(moves) * STEP),
            times,
            {},
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


def _replay(side: str, *, initial_stop: float | None = None, raw: dict[str, Any] | None = None):
    raw = raw or _spec()
    frame, plan = _frame(raw, side)
    return evaluate_managed_replay(
        raw,
        frame,
        plan,
        trade_id="trade-1",
        side=side,  # type: ignore[arg-type]
        entry_time_ms=0,
        entry_price=100.0,
        initial_stop_price=(98.0 if side == "long" else 102.0)
        if initial_stop is None
        else initial_stop,
    )


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        ("long", [98.0, 108.0, 110.0, 112.0, 119.0, 119.0, 119.0]),
        ("short", [102.0, 92.0, 90.0, 88.0, 81.0, 81.0, 81.0]),
    ],
)
def test_lock_then_trail_follow_monotonic_mfe(side: str, expected: list[float | None]) -> None:
    result = _replay(side)

    assert [bar.active_stop_price for bar in result.bars] == expected
    assert result.final_state.active_stop_rule_id == "trail"
    assert result.final_state.initial_risk == 2.0


def test_without_initial_risk_both_rules_fail_closed() -> None:
    raw = _spec()
    frame, plan = _frame(raw, "long")
    result = evaluate_managed_replay(
        raw,
        frame,
        plan,
        trade_id="trade-1",
        side="long",
        entry_time_ms=0,
        entry_price=100.0,
    )

    assert all(bar.active_stop_price is None for bar in result.bars)
    assert not any(event.event_type == "active_stop_updated" for event in result.events)


def test_non_tightening_r_candidates_do_not_relabel_legacy_stop() -> None:
    result = _replay("long", raw=_spec(legacy_distance=9.0))

    assert result.bars[1].active_stop_price == 109.0
    assert result.final_state.active_stop_rule_id == "trail"
    first_update = next(
        event for event in result.events if event.event_type == "active_stop_updated"
    )
    assert first_update.rule_id == "legacy"


@pytest.mark.parametrize(
    ("component_id", "params"),
    [
        ("initial_r_lock_stop", {"trigger_r": 0, "lock_r": 0}),
        ("initial_r_lock_stop", {"trigger_r": 6, "lock_r": -1}),
        ("initial_r_lock_stop", {"trigger_r": 6, "lock_r": 7}),
        ("initial_r_trailing_stop", {"trigger_r": 6, "trail_distance_r": 0}),
        ("initial_r_trailing_stop", {"trigger_r": 6, "trail_distance_r": 7}),
        ("initial_r_trailing_stop", {"trigger_r": float("inf"), "trail_distance_r": 2}),
    ],
)
def test_invalid_initial_r_parameters_fail(component_id: str, params: dict[str, object]) -> None:
    raw = _spec()
    management: Any = raw["trade_management"]
    management["exit_management"]["stop_management"] = [
        {
            "rule_id": "bad",
            "component_id": component_id,
            "activate_when": {"phase_at_least": "initial_risk"},
            "params": params,
        }
    ]
    frame, plan = _frame(raw, "long")

    with pytest.raises(InvalidRequestError):
        evaluate_managed_replay(
            raw,
            frame,
            plan,
            trade_id="trade-1",
            side="long",
            entry_time_ms=0,
            entry_price=100.0,
            initial_stop_price=98.0,
        )


def test_projection_uses_closed_formulas_and_opaque_references() -> None:
    raw = _spec()
    frame, plan = _frame(raw, "long")
    projection = build_historical_managed_projection(raw, frame, plan)
    assert projection is not None
    stops = [rule for rule in projection.rules if rule.kind == "stop_action"]

    assert [(rule.stop_formula, rule.trigger_distance_id) for rule in stops] == [
        ("initial_r_lock", "stop:lock:trigger"),
        ("initial_r_trailing", "stop:trail:trigger"),
    ]
    assert set(projection.distances["stop:lock:trigger"]) == {6.0}
    assert set(projection.distances["stop:lock:distance"]) == {4.0}
    assert set(projection.distances["stop:trail:distance"]) == {2.0}
    wires = [_serialize_rule(rule) for rule in stops]
    assert all("component_id" not in wire for wire in wires)
    assert all("trigger_r" not in wire for wire in wires)


@pytest.mark.parametrize("side", ["long", "short"])
def test_projection_reference_consumer_matches_single_trade(side: str) -> None:
    from test_ema_pullback_historical_managed_projection import _replay_from_projection

    raw = _spec()
    frame, plan = _frame(raw, side)
    initial_stop = 98.0 if side == "long" else 102.0
    oracle = _replay(side)
    projection = build_historical_managed_projection(raw, frame, plan)
    assert projection is not None

    projected = _replay_from_projection(
        projection,
        frame.market_bars,
        side=side,
        entry_index=0,
        entry_price=100.0,
        target_index=len(frame.market_bars) - 1,
        initial_stop_price=initial_stop,
    )
    assert [bar[1] for bar in projected] == [bar.active_stop_price for bar in oracle.bars]


def test_legacy_projection_wire_is_unchanged() -> None:
    rule = ManagedStopActionRule(
        kind="stop_action",
        rule_id="be",
        activation_phase="proven",
        distance_id="stop:be:distance",
    )

    assert _serialize_rule(rule) == {
        "kind": "stop_action",
        "rule_id": "be",
        "activation_phase": "proven",
        "distance_id": "stop:be:distance",
    }


def test_new_stop_features_require_no_extra_indicator() -> None:
    raw = _spec()
    without_stops = _spec()
    management: Any = without_stops["trade_management"]
    management["exit_management"]["stop_management"] = []

    with_plan = build_feature_plan_from_canonical_spec(raw)
    without_plan = build_feature_plan_from_canonical_spec(without_stops)
    assert with_plan.indicator_plan == without_plan.indicator_plan
