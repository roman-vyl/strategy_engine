from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.evaluate_live_entry_projection import (
    EvaluateLiveEntryProjection,
)
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.load_live_feature_frame import LoadLiveFeatureFrame
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import (
    LiveEntryProjectionRequest,
    StrategyRangeRequest,
    StrategySpecEnvelope,
)
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


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


def services() -> tuple[EvaluateLiveEntryProjection, EvaluateStrategyRange, StrategySpecEnvelope]:
    market_data = FakeMarketData()
    indicators = IndicatorRegistry()
    validate_plan = ValidateIndicatorPlan(indicators)
    indicator_eval = EvaluateIndicatorRange(indicators, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    evaluator = EmaPullbackRangeEvaluator(planner, indicator_eval)
    registry = StrategyRegistry(evaluator)
    validator = ValidateStrategySpec(registry, planner)
    loader = LoadLiveFeatureFrame(market_data, planner, indicator_eval, validator)
    strategy = StrategySpecEnvelope("ema_pullback", "v1", "live-1", spec())
    return (
        EvaluateLiveEntryProjection(loader),
        EvaluateStrategyRange(registry, validator),
        strategy,
    )


def test_live_entry_returns_stable_side_keys_and_provenance() -> None:
    live, _, strategy = services()
    result = live.execute(
        LiveEntryProjectionRequest(strategy, MarketStream("BTCUSDT.P", "5m"), 3_300_000)
    )
    assert result.source_config_hash == strategy.config_hash
    assert result.market_data_hash == "fixture-market-hash"
    assert set(result.plans_by_side) == {"long", "short"}
    assert result.plans_by_side["short"] is None
    plan = result.plans_by_side["long"]
    assert plan is not None
    assert plan.source_plan_bar_open_time_ms == 3_300_000
    assert Decimal(plan.initial_stop_price) < Decimal(plan.planned_entry_price)
    assert Decimal(plan.planned_entry_price) < Decimal(plan.initial_take_price)
    assert plan.locked_exit_profile in {"aligned", "countertrend", "neutral"}


def test_live_entry_matches_target_index_range_projection() -> None:
    live, range_eval, strategy = services()
    market = MarketStream("BTCUSDT.P", "5m")
    live_result = live.execute(LiveEntryProjectionRequest(strategy, market, 3_300_000))
    range_result = range_eval.execute(
        StrategyRangeRequest(strategy, market, TimeRange(0, 3_600_000))
    )
    target = -1
    projected = range_result.potential_entries["long"]
    plan = live_result.plans_by_side["long"]
    assert plan is not None
    assert plan.planned_entry_price == projected["entry_price"][target]
    assert plan.initial_stop_price == projected["stop_price"][target]
    assert plan.initial_take_price == projected["take_price"][target]
    assert plan.locked_exit_profile == range_result.exit_policy["profile_long"][target]


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
        ),
        potential_entries={
            "short": PotentialEntry("short", (100.0,), (101.0,), (99.0,)),
        },
    )

    plan = _plan_for_side(evaluation, "short", 0, 123)  # type: ignore[arg-type]
    assert plan is not None
    assert plan.side == "short"
    assert plan.locked_exit_profile == "countertrend"
