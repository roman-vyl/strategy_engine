from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.service.registries import IndicatorRegistry


def market_frame(values: list[str], *, timeframe: str = "5m") -> MarketFrame:
    step_ms = 300_000 if timeframe == "5m" else 60_000
    bars = tuple(
        MarketBar(
            open_time_ms=index * step_ms,
            open=Decimal(value),
            high=Decimal(value) + Decimal("1"),
            low=Decimal(value) - Decimal("1"),
            close=Decimal(value),
            volume=Decimal("10"),
        )
        for index, value in enumerate(values)
    )
    return MarketFrame(
        MarketStream("BTCUSDT.P", timeframe),
        TimeRange(0, len(values) * step_ms),
        bars,
        "fixture-hash",
    )


def feature(*, timeframe: str = "base", period: object = 3) -> PlannedFeature:
    return PlannedFeature(
        output_id=f"rsi_{timeframe}_{period}",
        kind="rsi",
        timeframe=timeframe,
        source="close",
        parameters={"period": period},
    )


def test_registry_exposes_rsi_schema() -> None:
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
    assert registry.get_schema("rsi")["compatibility_profile"] == "bbb_v1"


def test_base_rsi_uses_simple_rolling_gain_and_loss_means() -> None:
    result = RangeIndicatorEvaluator().evaluate(
        market_frame(["1", "2", "3", "2", "4"]),
        IndicatorPlan("1", (feature(period=3),)),
    )
    values = result.series["rsi_base_3"]
    assert values[:3] == (None, None, None)
    assert float(values[3]) == pytest.approx(66.66666666666666)
    assert float(values[4]) == pytest.approx(75.0)
    validity = result.validity["rsi_base_3"]
    assert validity.warmup_bars == 3
    assert validity.valid_from_ms == 900_000


def test_htf_rsi_requires_warmup_and_completed_bucket() -> None:
    values = [str(100 + index + (index % 5)) for index in range(72)]
    result = RangeIndicatorEvaluator().evaluate(
        market_frame(values),
        IndicatorPlan("1", (feature(timeframe="1h", period=3),)),
    )
    output = result.series["rsi_1h_3"]
    assert output[:48] == (None,) * 48
    assert output[48] is not None
    assert result.validity["rsi_1h_3"].valid_from_ms == 14_400_000


@pytest.mark.parametrize("period", [0, -1, True, 2.5, "3"])
def test_invalid_rsi_period_is_rejected(period: object) -> None:
    with pytest.raises(InvalidRequestError):
        IndicatorRegistry().validate_feature(feature(period=period))


def test_rsi_rejects_source_extra_parameters_and_dependencies() -> None:
    registry = IndicatorRegistry()
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(PlannedFeature("x", "rsi", "base", "high", {"period": 3}))
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "rsi", "base", "close", {"period": 3, "x": 1})
        )
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "rsi", "base", "close", {"period": 3}, ("y",))
        )
