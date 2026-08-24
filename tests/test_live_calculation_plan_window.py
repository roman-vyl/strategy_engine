"""Unit tests for PlanLiveHistoryStart."""

from __future__ import annotations

import random

from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.live_calculation.contracts import HistoryRequirement
from strategy_engine.strategies.live_calculation.indicator_requirements import (
    ResolveIndicatorHistoryRequirements,
)
from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart

_BASE_TF = "5m"
_BASE_MS = 5 * 60_000
_ANCHOR_MS = 2_000_000 * _BASE_MS  # arbitrary, far from epoch, base-aligned
_TOLERANCE = 1e-6  # explicit test-local tolerance, independent of the
# calibrated production default in indicator_requirements.py -- this test
# should not silently change meaning when that default is recalibrated.


def _plan(*features: PlannedFeature) -> IndicatorPlan:
    return IndicatorPlan(plan_version="v1", features=tuple(features))


def _minimal_spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "setups": [],
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            }
        },
    }
    spec.update(overrides)
    return spec


def test_additive_composition_stacks_strategy_lookback_behind_indicator_warmup() -> None:
    """RSI(14) blocker with lookback=20: the blocker's 20-bar window must sit
    entirely behind RSI's own warm-up, not overlap it (max() would under-count)."""
    plan = _plan(PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}))
    spec = _minimal_spec(
        components={
            "blockers": [
                {
                    "instance_id": "rsi-block",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "lookback": 20,
                    "rsi": {"timeframe": "base", "period": 14},
                }
            ],
            "trigger": {"component_id": "touch_anchor"},
        }
    )
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=_ANCHOR_MS,
    )
    expected_span_bars = 14 + 20  # indicator warm-up (finite RSI) + strategy lookback, summed
    expected_from = _ANCHOR_MS - expected_span_bars * _BASE_MS
    assert result.from_ms == expected_from
    # The blocker's earliest bar must be at or after RSI's own warm-up region.
    blocker_window_start_ms = expected_from + 14 * _BASE_MS
    assert blocker_window_start_ms + 20 * _BASE_MS == _ANCHOR_MS


def test_winning_requirements_are_separate_fields() -> None:
    plan = _plan(
        PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 5}),
        PlannedFeature("ema_1", "ema", "base", "close", {"period": 200}),
    )
    spec = _minimal_spec(
        setups=[
            {
                "instance_id": "untouched",
                "component_id": "untouched_anchor_setup",
                "params": {"lookback": 7},
            }
        ]
    )
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=_ANCHOR_MS,
    )
    assert "ema_1" in result.winning_indicator_requirement.reason
    assert "untouched_anchor_setup" in result.winning_strategy_requirement.reason
    assert result.winning_indicator_requirement != result.winning_strategy_requirement


def test_random_mixed_requirement_sets_pick_the_largest_per_source() -> None:
    from strategy_engine.strategies.live_calculation.indicator_requirements import (
        _ema_convergence_bars,
    )

    rng = random.Random(1234)
    for _ in range(20):
        rsi_period = rng.randint(2, 50)
        ema_period = rng.randint(2, 300)
        blocker_lookback = rng.randint(1, 100)
        plan = _plan(
            PlannedFeature("rsi_1", "rsi", "base", "close", {"period": rsi_period}),
            PlannedFeature("ema_1", "ema", "base", "close", {"period": ema_period}),
        )
        spec = _minimal_spec(
            components={
                "blockers": [
                    {
                        "instance_id": "rsi-block",
                        "component_id": "rsi_lookback_extreme_blocker",
                        "lookback": blocker_lookback,
                        "rsi": {"timeframe": "base", "period": rsi_period},
                    }
                ],
                "trigger": {"component_id": "touch_anchor"},
            }
        )
        result = PlanLiveHistoryStart(
            strategy_requirements=EmaPullbackLiveCalculationRequirements(),
            indicator_requirements=ResolveIndicatorHistoryRequirements(
                ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
            ),
        ).execute(
            raw_spec=spec,
            indicator_plan=plan,
            base_timeframe=_BASE_TF,
            history_anchor_open_time_ms=_ANCHOR_MS,
        )
        assert result.winning_strategy_requirement.bars == blocker_lookback
        # Ground-truth winner: whichever of RSI (finite) / EMA (convergence)
        # actually needs more base bars, computed independently of the
        # planner's own internal selection logic.
        expected_winner_bars = max(rsi_period, _ema_convergence_bars(ema_period, _TOLERANCE))
        assert result.winning_indicator_requirement.bars == expected_winner_bars


def test_no_htf_present_aligns_to_base_timeframe_grid_only() -> None:
    plan = _plan(PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}))
    spec = _minimal_spec()
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=_ANCHOR_MS,
    )
    assert result.from_ms % _BASE_MS == 0


def test_4h_requirement_aligns_from_ms_to_4h_utc_bucket_start() -> None:
    period = 5  # small period keeps the arithmetic easy to hand-verify
    plan = _plan(PlannedFeature("rsi_4h", "rsi", "4h", "close", {"period": period}))
    spec = _minimal_spec()
    four_h_ms = 4 * 3_600_000
    # Anchor chosen so anchor - span lands mid-bucket before alignment.
    anchor = 100 * four_h_ms + 2 * 3_600_000  # 2h into a 4h bucket
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=anchor,
    )
    assert result.from_ms % four_h_ms == 0


def test_1h_requirement_aligns_from_ms_to_1h_utc_bucket_start() -> None:
    plan = _plan(PlannedFeature("rsi_1h", "rsi", "1h", "close", {"period": 5}))
    spec = _minimal_spec()
    one_h_ms = 3_600_000
    anchor = 500 * one_h_ms + 35 * 60_000  # 35 minutes into an hour bucket
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=anchor,
    )
    assert result.from_ms % one_h_ms == 0


def test_multiple_simultaneous_htf_are_all_satisfied_at_once() -> None:
    plan = _plan(
        PlannedFeature("rsi_1h", "rsi", "1h", "close", {"period": 3}),
        PlannedFeature("ema_4h", "ema", "4h", "close", {"period": 5}),
    )
    spec = _minimal_spec()
    one_h_ms = 3_600_000
    four_h_ms = 4 * one_h_ms
    anchor = 1000 * four_h_ms + 90 * 60_000
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=anchor,
    )
    assert result.from_ms % one_h_ms == 0
    assert result.from_ms % four_h_ms == 0


class _FakeStrategyHistoryRequirements:
    """Minimal StrategyHistoryRequirements implementation with no dependency
    on ema_pullback -- proves PlanLiveHistoryStart is generic and works
    against any implementation of the Protocol, not just the production
    ema_pullback resolver."""

    def execute(self, raw_spec: object) -> tuple[HistoryRequirement, ...]:
        return (HistoryRequirement(timeframe="base", bars=42, reason="fake strategy requirement"),)


def test_planner_works_with_a_fake_strategy_history_requirements_implementation() -> None:
    plan = _plan(PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}))
    result = PlanLiveHistoryStart(
        strategy_requirements=_FakeStrategyHistoryRequirements()
    ).execute(
        raw_spec={},
        indicator_plan=plan,
        base_timeframe=_BASE_TF,
        history_anchor_open_time_ms=_ANCHOR_MS,
    )
    assert result.winning_strategy_requirement.bars == 42
    assert "fake strategy requirement" in result.winning_strategy_requirement.reason
    expected_span_bars = 14 + 42
    assert result.from_ms == _ANCHOR_MS - expected_span_bars * _BASE_MS
