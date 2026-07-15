from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.ema import EmaIndicatorEvaluator
from strategy_engine.service.registries import IndicatorRegistry


def market_frame(count: int = 24) -> MarketFrame:
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, count * 300_000)
    bars = tuple(
        MarketBar(
            open_time_ms=index * 300_000,
            open=Decimal(str(index + 1)),
            high=Decimal(str(index + 2)),
            low=Decimal(str(index)),
            close=Decimal(str(index + 1)),
            volume=Decimal("10"),
        )
        for index in range(count)
    )
    return MarketFrame(market, time_range, bars, "fixture-hash")


def feature(*, timeframe: str = "base", period: object = 3) -> PlannedFeature:
    return PlannedFeature(
        output_id=f"ema_close_{timeframe}_{period}",
        kind="ema",
        timeframe=timeframe,
        source="close",
        parameters={"period": period},
    )


def test_registry_exposes_ema_schema() -> None:
    registry = IndicatorRegistry()
    assert registry.list_definitions()[0]["indicator_id"] == "ema"
    assert registry.get_schema("ema")["supports_incremental"] is False


def test_base_ema_uses_adjust_false_from_first_bar() -> None:
    plan = IndicatorPlan("1", (feature(period=3),))
    result = EmaIndicatorEvaluator().evaluate(market_frame(4), plan)
    assert result.series["ema_close_base_3"] == ("1", "1.5", "2.25", "3.125")
    assert result.validity["ema_close_base_3"].valid_from_ms == 0
    assert result.validity["ema_close_base_3"].warmup_bars == 0


def test_htf_ema_is_not_visible_before_completed_bucket() -> None:
    plan = IndicatorPlan("1", (feature(timeframe="1h", period=2),))
    result = EmaIndicatorEvaluator().evaluate(market_frame(24), plan)
    values = result.series["ema_close_1h_2"]
    assert values[:12] == (None,) * 12
    assert values[12:] == ("12",) * 12
    assert result.validity["ema_close_1h_2"].valid_from_ms == 3_600_000


@pytest.mark.parametrize("period", [0, -1, True, 2.5, "3"])
def test_invalid_ema_period_is_rejected(period: object) -> None:
    with pytest.raises(InvalidRequestError):
        IndicatorRegistry().validate_feature(feature(period=period))


def test_invalid_source_dependencies_and_timeframe_are_rejected() -> None:
    registry = IndicatorRegistry()
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(PlannedFeature("x", "ema", "base", "volume", {"period": 3}))
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "ema", "base", "close", {"period": 3}, ("y",))
        )
    with pytest.raises(InvalidRequestError):
        EmaIndicatorEvaluator().evaluate(
            market_frame(),
            IndicatorPlan("1", (feature(timeframe="7m", period=3),)),
        )
