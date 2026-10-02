from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import EvaluationInvariantError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.build_live_strategy_feature_plan import (
    BuildLiveStrategyFeaturePlan,
)
from strategy_engine.strategies.application.evaluate_live_entry_projection import (
    EvaluateLiveEntryProjection,
    _normalize_desired_entry,
)
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.load_live_feature_frame import LoadLiveFeatureFrame
from strategy_engine.strategies.application.validate_live_strategy_spec import (
    ValidateLiveStrategySpec,
)
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import (
    LiveEntryPlan,
    LiveEntryProjectionRequest,
    LiveStrategySpec,
    StrategyRangeRequest,
)
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart


class FakeMarketData:
    def __init__(self) -> None:
        self.market = MarketStream("BTCUSDT.P", "5m")
        self.bars = tuple(
            MarketBar(
                i * 300_000,
                Decimal(str(i + 1)),
                Decimal(str(i + 2)),
                Decimal(str(i)),
                Decimal(str(i + 1)),
                Decimal("10"),
            )
            for i in range(12)
        )

    def load_bounds(self, market: MarketStream) -> StreamBounds:
        return StreamBounds(market, "ready", 0, 3_300_000)

    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame:
        del expected_market_data_hash
        bars = tuple(
            bar for bar in self.bars if time_range.from_ms <= bar.open_time_ms < time_range.to_ms
        )
        return MarketFrame(market, time_range, bars, "fixture-market-hash")


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
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "initial-stop",
                            "component_id": "constant_usd_stop_loss",
                            "exit_kind": "stop_loss",
                            "usd_distance": 0.25,
                        },
                        {
                            "instance_id": "initial-take",
                            "component_id": "constant_usd_take_profit",
                            "exit_kind": "take_profit",
                            "usd_distance": 0.5,
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


def services() -> tuple[EvaluateLiveEntryProjection, EvaluateStrategyRange, LiveStrategySpec]:
    market_data = FakeMarketData()
    indicators = IndicatorRegistry()
    validate_plan = ValidateIndicatorPlan(indicators)
    indicator_eval = EvaluateIndicatorRange(indicators, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    evaluator = EmaPullbackRangeEvaluator(planner, indicator_eval)
    registry = StrategyRegistry(evaluator)
    validator = ValidateStrategySpec(registry, planner)
    live_planner = BuildLiveStrategyFeaturePlan()
    live_validator = ValidateLiveStrategySpec(registry, live_planner)
    window_planner = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    )
    loader = LoadLiveFeatureFrame(
        market_data, live_planner, indicator_eval, live_validator, window_planner
    )
    strategy = LiveStrategySpec("ema_pullback", spec())
    return (
        EvaluateLiveEntryProjection(loader),
        EvaluateStrategyRange(registry, validator),
        strategy,
    )


def test_live_entry_returns_one_desired_entry() -> None:
    from dataclasses import fields

    from strategy_engine.strategies.contracts import LiveEntryProjectionResult

    live, _, strategy = services()
    live_strategy = LiveStrategySpec(
        strategy.strategy_id,
        strategy.raw_spec,
    )
    result = live.execute(
        LiveEntryProjectionRequest(
            live_strategy, MarketStream("BTCUSDT.P", "5m"), 3_300_000
        )
    )
    plan = result.desired_entry
    assert plan is not None
    assert plan.side == "long"
    assert plan.source_plan_bar_open_time_ms == 3_300_000
    assert Decimal(plan.initial_stop_price) < Decimal(plan.planned_entry_price)
    assert Decimal(plan.planned_entry_price) < Decimal(plan.initial_take_price)
    assert plan.locked_exit_profile in {"aligned", "countertrend", "neutral"}
    assert {item.name for item in fields(LiveEntryProjectionResult)} == {"desired_entry"}


def test_live_entry_matches_target_index_range_projection() -> None:
    live, range_eval, strategy = services()
    market = MarketStream("BTCUSDT.P", "5m")
    live_strategy = LiveStrategySpec(
        strategy.strategy_id,
        strategy.raw_spec,
    )
    live_result = live.execute(
        LiveEntryProjectionRequest(live_strategy, market, 3_300_000)
    )
    range_result = range_eval.execute_diagnostics(
        StrategyRangeRequest(strategy, market, TimeRange(0, 3_600_000))
    )
    target = -1
    projected = range_result.potential_entries["long"]
    plan = live_result.desired_entry
    assert plan is not None
    assert plan.planned_entry_price == projected["entry_price"][target]
    assert plan.initial_stop_price == projected["stop_price"][target]
    assert plan.initial_take_price == projected["take_price"][target]
    exit_policy = range_result.component_evidence["exit_policy"]
    assert plan.locked_exit_profile == exit_policy["profile_long"][target]


def _adapter_plan(side: str) -> LiveEntryPlan:
    if side == "long":
        stop, take = "99", "101"
    else:
        stop, take = "101", "99"
    return LiveEntryPlan(
        side=side,
        source_plan_bar_open_time_ms=123,
        planned_entry_price="100",
        initial_stop_price=stop,
        initial_take_price=take,
        locked_exit_profile="aligned",
    )


def test_live_entry_normalization_returns_null_for_zero_side_plans() -> None:
    assert _normalize_desired_entry({"long": None, "short": None}) is None


@pytest.mark.parametrize("side", ["long", "short"])
def test_live_entry_normalization_returns_the_single_side_plan(side: str) -> None:
    plan = _adapter_plan(side)
    result = _normalize_desired_entry(
        {"long": plan if side == "long" else None, "short": plan if side == "short" else None}
    )
    assert result is not None
    assert result.side == side
    assert result.source_plan_bar_open_time_ms == plan.source_plan_bar_open_time_ms
    assert result.planned_entry_price == plan.planned_entry_price
    assert result.initial_stop_price == plan.initial_stop_price
    assert result.initial_take_price == plan.initial_take_price
    assert result.locked_exit_profile == plan.locked_exit_profile


def test_live_entry_normalization_fails_closed_for_conflicting_side_plans() -> None:
    with pytest.raises(EvaluationInvariantError) as error:
        _normalize_desired_entry(
            {"long": _adapter_plan("long"), "short": _adapter_plan("short")}
        )

    assert error.value.code == "evaluation_invariant_broken"
    assert error.value.status_code == 500
    assert error.value.details == {"sides": ("long", "short")}


def test_live_entry_plan_projection_rejects_incomplete_and_invalid_geometry() -> None:
    from types import SimpleNamespace

    from strategy_engine.strategies.ema_pullback.live_projections.live_entry import (
        _plan_for_side,
    )
    from strategy_engine.strategies.ema_pullback.potential_entries import PotentialEntry

    exit_policy = SimpleNamespace(
        profile_long=("aligned",),
        profile_short=("countertrend",),
    )
    incomplete = SimpleNamespace(
        exit_policy=exit_policy,
        potential_entries={
            "long": PotentialEntry("long", (100.0,), (99.0,), (None,)),
        },
    )
    invalid = SimpleNamespace(
        exit_policy=exit_policy,
        potential_entries={
            "long": PotentialEntry("long", (100.0,), (101.0,), (102.0,)),
        },
    )

    assert _plan_for_side(incomplete, "long", 0, 0) is None  # type: ignore[arg-type]
    assert _plan_for_side(invalid, "long", 0, 0) is None  # type: ignore[arg-type]


def test_live_entry_plan_projection_accepts_short_geometry() -> None:
    from types import SimpleNamespace

    from strategy_engine.strategies.ema_pullback.live_projections.live_entry import (
        _plan_for_side,
    )
    from strategy_engine.strategies.ema_pullback.potential_entries import PotentialEntry

    evaluation = SimpleNamespace(
        exit_policy=SimpleNamespace(
            profile_long=("aligned",),
            profile_short=("countertrend",),
            partial_takes=(),
        ),
        potential_entries={
            "short": PotentialEntry("short", (100.0,), (101.0,), (99.0,)),
        },
    )

    plan = _plan_for_side(evaluation, "short", 0, 123)  # type: ignore[arg-type]
    assert plan is not None
    assert plan.side == "short"
    assert plan.locked_exit_profile == "countertrend"


# -- frozen partial take ladder (OpenSpec frozen-partial-take-ladder-v1) ------


def _leg(
    instance_id: str,
    *,
    group: str = "always_on",
    pct: float | None = None,
    distance: float | None = None,
    fraction: float = 0.25,
) -> object:
    from strategy_engine.strategies.ema_pullback.exits import PartialTakeRule

    return PartialTakeRule(
        instance_id=instance_id,
        component_id="pct_partial_take" if pct is not None else "atr_partial_take",
        group=group,
        fraction_of_initial=fraction,
        pct=pct,
        distance=(distance,),
    )


def _laddered_plan(side: str, take: float, legs: tuple[object, ...], profile: str = "aligned"):
    from types import SimpleNamespace

    from strategy_engine.strategies.ema_pullback.live_projections.live_entry import (
        _plan_for_side,
    )
    from strategy_engine.strategies.ema_pullback.potential_entries import PotentialEntry

    stop = 96.0 if side == "long" else 104.0
    evaluation = SimpleNamespace(
        exit_policy=SimpleNamespace(
            profile_long=(profile,),
            profile_short=(profile,),
            partial_takes=legs,
        ),
        potential_entries={side: PotentialEntry(side, (100.0,), (stop,), (take,))},
    )
    return _plan_for_side(evaluation, side, 0, 0)  # type: ignore[arg-type]


def test_live_partial_take_prices_long_and_short() -> None:
    legs = (_leg("atr", distance=3.0), _leg("pct", pct=0.01))
    long_plan = _laddered_plan("long", 116.0, legs)
    short_plan = _laddered_plan("short", 84.0, legs)
    assert long_plan is not None and short_plan is not None
    long_legs = long_plan.partial_takes
    assert [(leg.take_id, leg.price, leg.fraction_of_initial) for leg in long_legs] == [
        ("pct", "101", "0.25"),
        ("atr", "103", "0.25"),
    ]
    assert [(leg.take_id, leg.price) for leg in short_plan.partial_takes] == [
        ("pct", "99"),
        ("atr", "97"),
    ]
    assert long_plan.initial_take_price == "116"


def test_live_partial_take_beyond_final_take_is_returned() -> None:
    plan = _laddered_plan("long", 108.0, (_leg("far", pct=0.10),))
    assert plan is not None
    assert plan.initial_take_price == "108"
    assert [leg.price for leg in plan.partial_takes] == ["110"]


def test_live_partial_take_of_another_profile_is_excluded() -> None:
    plan = _laddered_plan("long", 116.0, (_leg("counter", group="countertrend", pct=0.01),))
    assert plan is not None
    assert plan.partial_takes == ()


def test_live_incomplete_partial_take_drops_the_plan() -> None:
    assert _laddered_plan("long", 116.0, (_leg("warming", distance=None),)) is None


def test_live_non_profit_side_partial_take_drops_the_plan() -> None:
    # A short leg whose price would not be positive has no valid price.
    assert _laddered_plan("short", 84.0, (_leg("deep", distance=100.0),)) is None
    assert _laddered_plan("long", 116.0, (_leg("zero", distance=0.0),)) is None
