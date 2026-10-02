"""`mfe_r` phase atom (`mfe-r-phase-threshold-v1`): MFE in multiples of the
trade's initial risk |entry - initial stop|, frozen at entry."""

from __future__ import annotations

from typing import Any

import pytest
from test_ema_pullback_managed import frame, spec

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.composite_spec import PHASE_ATOM_CHILDREN
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.historical_managed_projection import (
    build_historical_managed_projection,
)
from strategy_engine.strategies.ema_pullback.managed import (
    evaluate_managed_replay,
    evaluate_start_after_entry_managed_projection,
)


def _mfe_r_spec(threshold: float = 2.0) -> dict[str, Any]:
    raw = spec()
    management: Any = raw["trade_management"]
    management["exit_management"]["phase_rules"] = [
        {
            "rule_id": "to-proven",
            "to_phase": "proven",
            "condition": {"component_id": "mfe_r", "params": {"threshold": threshold}},
        }
    ]
    return raw


def _phase_bars(raw: dict[str, Any], **kwargs: Any) -> list[str]:
    feature_frame, plan = frame(raw)
    result = evaluate_managed_replay(
        raw,
        feature_frame,
        plan,
        trade_id="L1",
        side="long",
        entry_time_ms=0,
        entry_price=100.0,
        **kwargs,
    )
    return [bar.phase for bar in result.bars]


def test_threshold_is_in_multiples_of_initial_risk() -> None:
    # Bar i has high 102 + i: MFE distance 2, 3, 4, ... from entry 100.
    # Initial risk 1 -> 2R reached on bar 0; initial risk 2 -> bar 2 (4 = 2R).
    raw = _mfe_r_spec(2.0)
    assert _phase_bars(raw, initial_stop_price=99.0)[0] == "proven"
    phases = _phase_bars(raw, initial_stop_price=98.0)
    assert phases[:3] == ["initial_risk", "initial_risk", "proven"]


def test_short_side_mirrors() -> None:
    raw = _mfe_r_spec(1.0)
    feature_frame, plan = frame(raw)
    result = evaluate_managed_replay(
        raw,
        feature_frame,
        plan,
        trade_id="S1",
        side="short",
        entry_time_ms=0,
        entry_price=100.0,
        initial_stop_price=105.0,
    )
    # Lows 99, 100, ... never go 5 below 100: no transition.
    assert {bar.phase for bar in result.bars} == {"initial_risk"}


def test_without_initial_stop_the_atom_is_unmet() -> None:
    assert set(_phase_bars(_mfe_r_spec(0.5))) == {"initial_risk"}


def test_live_start_after_entry_uses_the_receipt_initial_stop() -> None:
    raw = _mfe_r_spec(2.0)
    feature_frame, plan = frame(raw)
    projection = evaluate_start_after_entry_managed_projection(
        raw,
        feature_frame,
        plan,
        side="long",
        entry_time_ms=0,
        planned_entry_price=100.0,
        initial_stop_price=98.0,
        initial_take_price=130.0,
        target_time_ms=feature_frame.time_ms[-1],
    )
    assert projection.replay.final_state.phase == "proven"


def test_projection_threshold_is_constant_r_with_mfe_r_metric() -> None:
    raw = _mfe_r_spec(6.0)
    feature_frame, plan = frame(raw)
    projection = build_historical_managed_projection(raw, feature_frame, plan)
    assert projection is not None
    (rule,) = [r for r in projection.rules if r.kind == "phase_transition"]
    assert rule.trade_metric == "mfe_r"
    assert rule.distance_id is not None
    assert set(projection.distances[rule.distance_id]) == {6.0}


@pytest.mark.parametrize("threshold", [0, -1.0, "x", None])
def test_threshold_must_be_positive_number(threshold: object) -> None:
    raw = _mfe_r_spec(1.0)
    management: Any = raw["trade_management"]
    management["exit_management"]["phase_rules"][0]["condition"]["params"]["threshold"] = threshold
    feature_frame, plan = frame(raw)
    with pytest.raises(InvalidRequestError):
        evaluate_managed_replay(
            raw,
            feature_frame,
            plan,
            trade_id="L1",
            side="long",
            entry_time_ms=0,
            entry_price=100.0,
            initial_stop_price=99.0,
        )


def test_mfe_r_is_a_composite_trade_child() -> None:
    assert "mfe_r" in PHASE_ATOM_CHILDREN


def test_planning_needs_no_extra_features() -> None:
    plan = build_feature_plan_from_canonical_spec(_mfe_r_spec())
    assert not plan.adx_dmi_columns
