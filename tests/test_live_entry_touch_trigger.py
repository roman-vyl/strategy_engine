"""`touch_trigger` live-entry mode (OpenSpec touch-signal-close-entry-v1)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.strategies.application.evaluate_live_entry_projection import (
    EvaluateLiveEntryProjection,
)
from strategy_engine.strategies.application.load_live_feature_frame import (
    LiveFeatureFrameRequest,
)
from strategy_engine.strategies.contracts import LiveEntryProjectionRequest, LiveStrategySpec
from strategy_engine.strategies.ema_pullback.evaluation import evaluate_ema_pullback_frame
from strategy_engine.strategies.ema_pullback.live_projections.live_entry import (
    EmaPullbackLiveEntryProjectionAdapter,
    _touch_trigger_plan_for_side,
)
from strategy_engine.strategies.live_projections.defaults import (
    build_live_entry_projection_registry,
)
from tests.test_live_entry_projection import FakeMarketData, services, spec

MARKET = MarketStream("BTCUSDT.P", "5m")


# -- unit: plan from the final entry mask at the signal-bar close -------------


def _frame(close: float) -> SimpleNamespace:
    bar = MarketBar(0, Decimal("1"), Decimal("1"), Decimal("1"), Decimal(str(close)), Decimal("1"))
    return SimpleNamespace(market_arrays=None, time_ms=(0,), market_bars=(bar,))


def _evaluation(
    side: str,
    *,
    signal: bool,
    trigger: str = "touch_anchor",
    stop: float | None = 1.2,
    take: float | None = 6.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        triggers=(SimpleNamespace(side=side, trigger=SimpleNamespace(component_id=trigger)),),
        entries=(SimpleNamespace(side=side, entry_allowed=(signal,)),),
        exit_policy=SimpleNamespace(
            stop_loss_distance_long=(stop,),
            take_profit_distance_long=(take,),
            stop_loss_distance_short=(stop,),
            take_profit_distance_short=(take,),
            profile_long=("aligned",),
            profile_short=("countertrend",),
            partial_takes=(),
        ),
        potential_entries={},
    )


def test_signal_bar_plan_is_priced_at_the_close() -> None:
    plan = _touch_trigger_plan_for_side(
        _evaluation("long", signal=True),
        _frame(100.5),
        "long",
        0,
        123,  # type: ignore[arg-type]
    )
    assert plan is not None
    assert (plan.planned_entry_price, plan.initial_stop_price, plan.initial_take_price) == (
        "100.5",
        "99.3",
        "106.5",
    )
    assert plan.source_plan_bar_open_time_ms == 123
    assert plan.locked_exit_profile == "aligned"
    assert plan.partial_takes == ()


def test_short_signal_bar_plan_is_mirrored() -> None:
    plan = _touch_trigger_plan_for_side(
        _evaluation("short", signal=True),
        _frame(100.5),
        "short",
        0,
        0,  # type: ignore[arg-type]
    )
    assert plan is not None
    assert (plan.initial_stop_price, plan.initial_take_price) == ("101.7", "94.5")


@pytest.mark.parametrize(
    "evaluation",
    [
        _evaluation("long", signal=False),  # armed without touch, or vote-blocked touch
        _evaluation("long", signal=True, trigger="reclaim_anchor"),
        _evaluation("long", signal=True, stop=None),
        _evaluation("long", signal=True, take=0.0),
    ],
)
def test_no_plan_without_a_complete_touch_signal(evaluation: SimpleNamespace) -> None:
    assert _touch_trigger_plan_for_side(evaluation, _frame(100.5), "long", 0, 0) is None  # type: ignore[arg-type]


def test_side_not_evaluated_has_no_plan() -> None:
    plan = _touch_trigger_plan_for_side(
        _evaluation("long", signal=True),
        _frame(100.5),
        "short",
        0,
        0,  # type: ignore[arg-type]
    )
    assert plan is None


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="live_entry_mode"):
        EmaPullbackLiveEntryProjectionAdapter(live_entry_mode="close")  # type: ignore[arg-type]


# -- end to end through the live-entry use case --------------------------------


def _live(
    mode: str, market_data: FakeMarketData | None = None
) -> tuple[EvaluateLiveEntryProjection, object, LiveStrategySpec]:
    default_live, _, strategy = services(market_data)
    loader = default_live._live_frame_loader
    return (
        EvaluateLiveEntryProjection(loader, build_live_entry_projection_registry(mode)),  # type: ignore[arg-type]
        loader,
        strategy,
    )


TARGETS = tuple(i * 300_000 for i in range(5, 12))


class DippingMarketData(FakeMarketData):
    """Rising closes whose lows stay above the anchor, except bars 8 and 10
    that dip through it and close back above (touch signal bars)."""

    def __init__(self) -> None:
        super().__init__()
        bars = []
        for i in range(12):
            close = Decimal(str(10 + 2 * i))
            low = close - (Decimal("6") if i in (8, 10) else Decimal("0.5"))
            bars.append(MarketBar(i * 300_000, close - 1, close + 1, low, close, Decimal("10")))
        self.bars = tuple(bars)


def test_touch_trigger_plans_exactly_on_entry_mask_bars_at_the_close() -> None:
    market_data = DippingMarketData()
    live, loader, strategy = _live("touch_trigger", market_data)
    anchor_live, _, _ = _live("ema_anchor", market_data)
    closes = {bar.open_time_ms: bar.close for bar in market_data.bars}
    seen_plan = seen_null = False
    for target in TARGETS:
        bundle = loader.execute(  # type: ignore[attr-defined]
            LiveFeatureFrameRequest(strategy, MARKET, target, target)
        )
        evaluation = evaluate_ema_pullback_frame(strategy, bundle.frame, bundle.planned_features)
        signal = next(e for e in evaluation.entries if e.side == "long").entry_allowed[
            bundle.target_index
        ]
        plan = live.execute(LiveEntryProjectionRequest(strategy, MARKET, target)).desired_entry
        if signal:
            seen_plan = True
            assert plan is not None
            assert Decimal(plan.planned_entry_price) == closes[target]
            assert plan.source_plan_bar_open_time_ms == target
        else:
            seen_null = True
            assert plan is None
            # armed bar without touch: the old mode still plans at the anchor
            anchor_plan = anchor_live.execute(
                LiveEntryProjectionRequest(strategy, MARKET, target)
            ).desired_entry
            assert anchor_plan is not None
    assert seen_plan and seen_null


def test_ema_anchor_mode_is_the_default_answer() -> None:
    default_live, _, strategy = services()
    anchor_live, _, _ = _live("ema_anchor")
    for target in TARGETS:
        request = LiveEntryProjectionRequest(strategy, MARKET, target)
        assert anchor_live.execute(request) == default_live.execute(request)


def test_touch_trigger_spec_without_touch_anchor_returns_null() -> None:
    live, _, _ = _live("touch_trigger")
    raw = spec()
    raw["components"] = {"blockers": [], "trigger": {"component_id": "reclaim_anchor"}}  # type: ignore[index]
    strategy = LiveStrategySpec("ema_pullback", raw)
    result = live.execute(LiveEntryProjectionRequest(strategy, MARKET, TARGETS[-1]))
    assert result.desired_entry is None
