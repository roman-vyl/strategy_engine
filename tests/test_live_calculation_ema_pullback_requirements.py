"""Unit tests for EmaPullbackLiveCalculationRequirements."""

from __future__ import annotations

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)


def _spec(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "setups": [
            {
                "instance_id": "untouched",
                "component_id": "untouched_anchor_setup",
                "params": {"lookback": 50},
            }
        ],
        "components": {
            "blockers": [
                {
                    "instance_id": "rsi-block",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "lookback": 20,
                    "rsi": {"timeframe": "1h", "period": 14},
                }
            ],
            "trigger": {"component_id": "reclaim_anchor", "lookback": 1},
        },
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "sl",
                            "component_id": "atr_stop_loss",
                            "exit_kind": "stop_loss",
                            "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                        }
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            }
        },
    }
    base.update(overrides)
    return base


def test_setup_lookback_is_read_from_params() -> None:
    # default spec has params={"lookback": 50}, active_bars defaults to 3 in
    # the evaluator -> bars = lookback + active_bars - 1 = 52 (see
    # test_untouched_anchor_setup_accounts_for_active_bars for why).
    reqs = EmaPullbackLiveCalculationRequirements().execute(_spec())
    setup_reqs = [r for r in reqs if "untouched_anchor_setup" in r.reason]
    assert setup_reqs[0].bars == 52
    assert setup_reqs[0].timeframe == "base"


def test_untouched_anchor_setup_accounts_for_active_bars() -> None:
    """touch_active at target can be driven by a first_touch up to
    active_bars-1 bars before target, and that first_touch's own
    untouched_prior needs `lookback` bars of touch history before it -- so
    the requirement must be lookback + active_bars - 1, not just lookback."""
    spec = _spec(
        setups=[
            {
                "instance_id": "untouched",
                "component_id": "untouched_anchor_setup",
                "params": {"lookback": 50, "active_bars": 3},
            }
        ]
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    setup_reqs = [r for r in reqs if "untouched_anchor_setup" in r.reason]
    assert setup_reqs[0].bars == 52


def test_blocker_lookback_counted_on_base_axis_not_indicator_timeframe() -> None:
    """The blocker reads a 1h RSI but its own lookback=20 must stay 20 base
    bars, never 20 * 1h -- the axis rule (design.md Decision 4b)."""
    reqs = EmaPullbackLiveCalculationRequirements().execute(_spec())
    blocker_reqs = [r for r in reqs if "rsi_lookback_extreme_blocker" in r.reason]
    assert blocker_reqs[0].bars == 20
    assert blocker_reqs[0].timeframe == "base"


def test_anchor_stack_width_setup_uses_width_lookback_bars() -> None:
    spec = _spec(
        setups=[
            {
                "instance_id": "width",
                "component_id": "anchor_stack_width_setup",
                "params": {"width_lookback_bars": 80},
            }
        ]
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    assert any(r.bars == 80 and "anchor_stack_width_setup" in r.reason for r in reqs)


def _bounce_spec(anchor_period: int, *, fast: int = 20, slow: int = 200, **overrides: object):
    return _spec(
        anchor_stack={
            "fast": {"source": "close", "timeframe": "base", "period": fast},
            "anchor": {"source": "close", "timeframe": "base", "period": anchor_period},
            "slow": {"source": "close", "timeframe": "base", "period": slow},
        },
        setups=[
            {
                "instance_id": "bounce",
                "component_id": "ema_bounce_counter_setup",
                "params": {"touch_lookback_bars": 10},
            }
        ],
        **overrides,
    )


def _bounce_bars(spec: dict[str, object]) -> int:
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    matches = [r for r in reqs if "ema_bounce_counter_setup" in r.reason]
    assert len(matches) == 1
    return matches[0].bars


# -- V1 anchor-EMA tier boundaries (tasks.md 5.12) --------------------------
# anchor <= 200        -> 2500
# 200 < anchor <= 500  -> 6000
# 500 < anchor <= 1000 -> 15000
# anchor > 1000        -> fail closed


@pytest.mark.parametrize("anchor", [100, 199, 200])
def test_bounce_tier_1_anchor_up_to_200_selects_2500(anchor: int) -> None:
    assert _bounce_bars(_bounce_spec(anchor)) == 2500


@pytest.mark.parametrize("anchor", [201, 499, 500])
def test_bounce_tier_2_anchor_201_to_500_selects_6000(anchor: int) -> None:
    assert _bounce_bars(_bounce_spec(anchor)) == 6000


@pytest.mark.parametrize("anchor", [501, 999, 1000])
def test_bounce_tier_3_anchor_501_to_1000_selects_15000(anchor: int) -> None:
    assert _bounce_bars(_bounce_spec(anchor)) == 15000


@pytest.mark.parametrize("anchor", [1001, 1500])
def test_bounce_anchor_above_1000_fails_closed(anchor: int) -> None:
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(_bounce_spec(anchor))


def test_bounce_reason_reports_anchor_period_and_selected_bars() -> None:
    reqs = EmaPullbackLiveCalculationRequirements().execute(_bounce_spec(500))
    bounce = [r for r in reqs if "ema_bounce_counter_setup" in r.reason][0]
    assert "anchor_period=500" in bounce.reason
    assert "6000" in bounce.reason


# -- fast/slow EMA must NOT affect tier selection ---------------------------


@pytest.mark.parametrize(
    ("fast", "slow"),
    [(100, 500), (50, 300), (199, 1000)],
)
def test_bounce_tier_ignores_fast_and_slow_at_anchor_200(fast: int, slow: int) -> None:
    assert _bounce_bars(_bounce_spec(200, fast=fast, slow=slow)) == 2500


@pytest.mark.parametrize(
    ("fast", "slow"),
    [(50, 600), (400, 1000), (10, 2000)],
)
def test_bounce_tier_ignores_fast_and_slow_at_anchor_500(fast: int, slow: int) -> None:
    assert _bounce_bars(_bounce_spec(500, fast=fast, slow=slow)) == 6000


@pytest.mark.parametrize(
    ("fast", "slow"),
    [(100, 1200), (500, 2000), (999, 1001)],
)
def test_bounce_tier_ignores_fast_and_slow_at_anchor_1000(fast: int, slow: int) -> None:
    assert _bounce_bars(_bounce_spec(1000, fast=fast, slow=slow)) == 15000


# -- conditional presence: bounce requirement only exists when the setup is
# actually configured; anchor > 1000 is only a problem when bounce is present


def test_no_bounce_setup_means_no_bounce_requirement_even_with_large_anchor() -> None:
    spec = _spec(
        anchor_stack={
            "fast": {"source": "close", "timeframe": "base", "period": 500},
            "anchor": {"source": "close", "timeframe": "base", "period": 1500},
            "slow": {"source": "close", "timeframe": "base", "period": 2000},
        },
        setups=[],
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    assert not any("ema_bounce_counter_setup" in r.reason for r in reqs)


def test_no_bounce_setup_with_anchor_over_1000_does_not_fail_closed() -> None:
    spec = _spec(
        anchor_stack={
            "fast": {"source": "close", "timeframe": "base", "period": 500},
            "anchor": {"source": "close", "timeframe": "base", "period": 1200},
            "slow": {"source": "close", "timeframe": "base", "period": 2000},
        },
        setups=[],
    )
    # Must not raise -- the bounce-specific fail-closed check only applies
    # when ema_bounce_counter_setup is actually configured.
    EmaPullbackLiveCalculationRequirements().execute(spec)


def test_bounce_present_at_anchor_500_adds_requirement() -> None:
    reqs = EmaPullbackLiveCalculationRequirements().execute(_bounce_spec(500))
    assert any(r.bars == 6000 and "ema_bounce_counter_setup" in r.reason for r in reqs)


def test_bounce_present_at_anchor_over_1000_fails_closed_specifically() -> None:
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(_bounce_spec(1500))


# -- planner-level aggregation regression (existing composition unchanged) --


def test_planner_winning_strategy_requirement_is_bounce_when_it_is_deepest() -> None:
    from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
    from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart

    spec = _bounce_spec(500)  # bounce -> 6000 bars, larger than the rsi blocker's 20
    plan = IndicatorPlan(
        plan_version="v1",
        features=(PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}),),
    )
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe="5m",
        history_anchor_open_time_ms=10_000_000_000,
    )
    assert "ema_bounce_counter_setup" in result.winning_strategy_requirement.reason
    assert result.winning_strategy_requirement.bars == 6000


def test_planner_winning_strategy_requirement_is_not_bounce_when_another_is_deeper() -> None:
    from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
    from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart

    # anchor=100 -> bounce tier = 2500; untouched_anchor_setup lookback=9000
    # is deeper and must win instead -- proves bounce doesn't special-case
    # its way to always winning.
    spec = _spec(
        anchor_stack={
            "fast": {"source": "close", "timeframe": "base", "period": 20},
            "anchor": {"source": "close", "timeframe": "base", "period": 100},
            "slow": {"source": "close", "timeframe": "base", "period": 200},
        },
        setups=[
            {
                "instance_id": "bounce",
                "component_id": "ema_bounce_counter_setup",
                "params": {},
            },
            {
                "instance_id": "untouched",
                "component_id": "untouched_anchor_setup",
                "params": {"lookback": 9000, "active_bars": 1},
            },
        ],
    )
    plan = IndicatorPlan(
        plan_version="v1",
        features=(PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}),),
    )
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe="5m",
        history_anchor_open_time_ms=10_000_000_000,
    )
    assert "untouched_anchor_setup" in result.winning_strategy_requirement.reason
    assert result.winning_strategy_requirement.bars == 9000


def test_planner_indicator_winner_semantics_unaffected_by_bounce_presence() -> None:
    from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
    from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart

    spec = _bounce_spec(200)  # bounce -> 2500 bars (strategy side)
    plan = IndicatorPlan(
        plan_version="v1",
        features=(
            PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}),
            PlannedFeature("ema_1", "ema", "4h", "close", {"period": 200}),
        ),
    )
    result = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    ).execute(
        raw_spec=spec,
        indicator_plan=plan,
        base_timeframe="5m",
        history_anchor_open_time_ms=10_000_000_000,
    )
    # Existing indicator-side winner semantics (largest span wins) untouched
    # by bounce's presence on the strategy side -- the two sides remain
    # independent, summed, not compared against each other for "winning".
    assert "ema_1" in result.winning_indicator_requirement.reason


def test_ema_close_loss_exit_uses_confirm_bars() -> None:
    spec = _spec(
        trade_management={
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "close-loss",
                            "component_id": "ema_close_loss_exit",
                            "confirm_bars": 3,
                            "ema": {"timeframe": "base", "period": 20},
                        }
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            }
        }
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    exit_req = [r for r in reqs if "ema_close_loss_exit" in r.reason][0]
    assert exit_req.bars == 3


def test_ema_cross_loss_exit_adds_one_bar_for_shift() -> None:
    spec = _spec(
        trade_management={
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "cross-loss",
                            "component_id": "ema_cross_loss_exit",
                            "confirm_bars": 3,
                            "fast_ema": {"timeframe": "base", "period": 20},
                            "slow_ema": {"timeframe": "base", "period": 50},
                        }
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            }
        }
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    exit_req = [r for r in reqs if "ema_cross_loss_exit" in r.reason][0]
    assert exit_req.bars == 4


def test_distance_stop_exit_contributes_zero_additional_lookback() -> None:
    reqs = EmaPullbackLiveCalculationRequirements().execute(_spec())
    stop_req = [r for r in reqs if "atr_stop_loss" in r.reason][0]
    assert stop_req.bars == 0


def test_phase_runtime_exit_in_runtime_exits_contributes_zero_and_does_not_fail_closed() -> None:
    """managed.py dispatches phase_runtime_exit in its runtime-exit condition
    function (a current-bar exit_price == "close" check), not in the
    phase_rules condition dispatch -- a spec using it in
    exit_management.runtime_exits must resolve to zero lookback, not fail
    closed."""
    spec = _spec(
        trade_management={
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {
                "runtime_exits": [
                    {
                        "instance_id": "phase-exit",
                        "component_id": "phase_runtime_exit",
                        "params": {"exit_price": "close"},
                    }
                ]
            },
        }
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    phase_reqs = [r for r in reqs if "phase_runtime_exit" in r.reason]
    assert len(phase_reqs) == 1
    assert phase_reqs[0].bars == 0
    assert phase_reqs[0].timeframe == "base"


def test_unrecognized_setup_component_fails_closed() -> None:
    spec = _spec(
        setups=[{"instance_id": "x", "component_id": "some_future_setup", "params": {}}]
    )
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(spec)


def test_unrecognized_blocker_component_fails_closed() -> None:
    spec = _spec()
    spec["components"] = {
        "blockers": [{"instance_id": "x", "component_id": "some_future_blocker"}],
        "trigger": {"component_id": "reclaim_anchor", "lookback": 1},
    }
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(spec)


def test_unrecognized_exit_component_fails_closed() -> None:
    spec = _spec()
    spec["trade_management"] = {
        "exit_policy": {
            "always_on": {
                "exits": [{"instance_id": "x", "component_id": "some_future_exit"}]
            },
            "profiles": {
                "aligned": {"exits": []},
                "countertrend": {"exits": []},
                "neutral": {"exits": []},
            },
        }
    }
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(spec)


def test_trigger_accepts_bare_string_shorthand_like_the_real_evaluator() -> None:
    """triggers._trigger_rule accepts `trigger: "touch_anchor"` as well as the
    object form -- the resolver must not fail closed on a spec shape the real
    evaluator already accepts."""
    spec = _spec()
    spec["components"] = {
        "blockers": [],
        "trigger": "touch_anchor",
    }
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    trigger_req = [r for r in reqs if "components.trigger" in r.reason][0]
    assert trigger_req.bars == 0


def test_trigger_string_shorthand_for_reclaim_uses_default_lookback() -> None:
    spec = _spec()
    spec["components"] = {"blockers": [], "trigger": "reclaim_anchor"}
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    trigger_req = [r for r in reqs if "components.trigger" in r.reason][0]
    assert trigger_req.bars == 1


def test_htf_context_contributes_zero_additional_lookback() -> None:
    spec = _spec(
        contexts={
            "htf": {
                "component_id": "htf_context",
                "timeframe": "4h",
                "source": "close",
                "fast_period": 20,
                "anchor_period": 50,
                "slow_period": 200,
            }
        }
    )
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    context_reqs = [r for r in reqs if "htf_context" in r.reason]
    assert len(context_reqs) == 1
    assert context_reqs[0].bars == 0


def test_unrecognized_context_provider_fails_closed() -> None:
    spec = _spec(contexts={"htf": {"component_id": "some_future_context"}})
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(spec)


def test_default_direction_contributes_zero_additional_lookback() -> None:
    reqs = EmaPullbackLiveCalculationRequirements().execute(_spec())
    direction_reqs = [r for r in reqs if "components.direction" in r.reason]
    assert len(direction_reqs) == 1
    assert direction_reqs[0].bars == 0


def test_unrecognized_direction_component_fails_closed() -> None:
    spec = _spec()
    spec["components"] = {
        "blockers": [],
        "trigger": {"component_id": "reclaim_anchor", "lookback": 1},
        "direction": "some_future_direction",
    }
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(spec)


def test_default_risk_contributes_zero_additional_lookback() -> None:
    reqs = EmaPullbackLiveCalculationRequirements().execute(_spec())
    risk_reqs = [r for r in reqs if "components.risk" in r.reason]
    assert len(risk_reqs) == 1
    assert risk_reqs[0].bars == 0


def test_risk_accepts_object_form_like_the_real_evaluator() -> None:
    spec = _spec()
    spec["components"] = {
        "blockers": [],
        "trigger": {"component_id": "reclaim_anchor", "lookback": 1},
        "risk": {"component_id": "no_risk_filter"},
    }
    reqs = EmaPullbackLiveCalculationRequirements().execute(spec)
    risk_reqs = [r for r in reqs if "components.risk" in r.reason]
    assert risk_reqs[0].bars == 0


def test_unrecognized_risk_component_fails_closed() -> None:
    spec = _spec()
    spec["components"] = {
        "blockers": [],
        "trigger": {"component_id": "reclaim_anchor", "lookback": 1},
        "risk": "some_future_risk_filter",
    }
    with pytest.raises(InvalidRequestError):
        EmaPullbackLiveCalculationRequirements().execute(spec)
