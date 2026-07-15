from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.service.registries import IndicatorRegistry


def market_frame(count: int = 36) -> MarketFrame:
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, count * 300_000)
    bars = tuple(
        MarketBar(
            open_time_ms=index * 300_000,
            open=Decimal(str(100 + index)),
            high=Decimal(str(102 + index)),
            low=Decimal(str(99 + index)),
            close=Decimal(str(101 + index)),
            volume=Decimal("10"),
        )
        for index in range(count)
    )
    return MarketFrame(market, time_range, bars, "fixture-hash")


def feature(*, timeframe: str = "base", period: object = 3) -> PlannedFeature:
    return PlannedFeature(
        output_id=f"atr_{timeframe}_{period}",
        kind="atr",
        timeframe=timeframe,
        source="close",
        parameters={"period": period},
    )


def test_registry_exposes_atr_schema() -> None:
    registry = IndicatorRegistry()
    assert [item["indicator_id"] for item in registry.list_definitions()] == [
        "ema",
        "atr",
        "atr_distance",
        "rsi",
        "adx",
        "di_plus",
        "di_minus",
    ]
    assert registry.get_schema("atr")["compatibility_profile"] == "bbb_v1"


def test_base_atr_is_simple_rolling_true_range_mean() -> None:
    result = RangeIndicatorEvaluator().evaluate(
        market_frame(5),
        IndicatorPlan("1", (feature(period=3),)),
    )
    assert result.series["atr_base_3"] == (None, None, "3", "3", "3")
    validity = result.validity["atr_base_3"]
    assert validity.warmup_bars == 2
    assert validity.valid_from_ms == 600_000


def test_htf_atr_requires_warmup_and_completed_bucket() -> None:
    result = RangeIndicatorEvaluator().evaluate(
        market_frame(48),
        IndicatorPlan("1", (feature(timeframe="1h", period=2),)),
    )
    values = result.series["atr_1h_2"]
    assert values[:24] == (None,) * 24
    assert values[24:] == ("14",) * 24
    assert result.validity["atr_1h_2"].valid_from_ms == 7_200_000


@pytest.mark.parametrize("period", [0, -1, True, 2.5, "3"])
def test_invalid_atr_period_is_rejected(period: object) -> None:
    with pytest.raises(InvalidRequestError):
        IndicatorRegistry().validate_feature(feature(period=period))


def test_atr_rejects_source_extra_parameters_and_dependencies() -> None:
    registry = IndicatorRegistry()
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(PlannedFeature("x", "atr", "base", "high", {"period": 3}))
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "atr", "base", "close", {"period": 3, "x": 1})
        )
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "atr", "base", "close", {"period": 3}, ("y",))
        )
