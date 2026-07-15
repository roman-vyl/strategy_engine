from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.service.registries import IndicatorRegistry


def market_frame(count: int = 12) -> MarketFrame:
    step_ms = 300_000
    bars = tuple(
        MarketBar(
            open_time_ms=index * step_ms,
            open=Decimal(str(100 + index)),
            high=Decimal(str(102 + index)),
            low=Decimal(str(99 + index)),
            close=Decimal(str(101 + index)),
            volume=Decimal("10"),
        )
        for index in range(count)
    )
    return MarketFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(0, count * step_ms),
        bars,
        "fixture-hash",
    )


def plan(multiplier: object = 2.5) -> IndicatorPlan:
    return IndicatorPlan(
        "1",
        (
            PlannedFeature(
                "atr_close_base_3",
                "atr",
                "base",
                "close",
                {"period": 3},
            ),
            PlannedFeature(
                "atr_close_base_3_x2p5",
                "atr_distance",
                "base",
                None,
                {"multiplier": multiplier},
                ("atr_close_base_3",),
            ),
        ),
    )


def test_registry_exposes_atr_distance() -> None:
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
    schema = registry.get_schema("atr_distance")
    assert schema is not None
    assert schema["derived_from"] == "atr"


def test_atr_distance_reuses_dependency_and_preserves_validity() -> None:
    result = RangeIndicatorEvaluator().evaluate(market_frame(), plan())
    atr = result.series["atr_close_base_3"]
    distance = result.series["atr_close_base_3_x2p5"]
    assert distance[:2] == (None, None)
    for base, derived in zip(atr, distance, strict=True):
        if base is None:
            assert derived is None
        else:
            assert float(derived) == pytest.approx(float(base) * 2.5)
    assert result.validity["atr_close_base_3_x2p5"] == result.validity["atr_close_base_3"]


@pytest.mark.parametrize("multiplier", [0, -1, True, "2", None])
def test_invalid_multiplier_is_rejected(multiplier: object) -> None:
    with pytest.raises(InvalidRequestError):
        ValidateIndicatorPlan(IndicatorRegistry()).execute(plan(multiplier))


def test_dependency_must_be_earlier_atr_with_matching_timeframe() -> None:
    validator = ValidateIndicatorPlan(IndicatorRegistry())
    derived = PlannedFeature(
        "distance",
        "atr_distance",
        "base",
        None,
        {"multiplier": 2},
        ("base",),
    )
    atr = PlannedFeature("base", "atr", "base", "close", {"period": 3})
    with pytest.raises(InvalidRequestError):
        validator.execute(IndicatorPlan("1", (derived, atr)))
    ema = PlannedFeature("base", "ema", "base", "close", {"period": 3})
    with pytest.raises(InvalidRequestError):
        validator.execute(IndicatorPlan("1", (ema, derived)))
    htf_derived = PlannedFeature(
        "distance",
        "atr_distance",
        "1h",
        None,
        {"multiplier": 2},
        ("base",),
    )
    with pytest.raises(InvalidRequestError):
        validator.execute(IndicatorPlan("1", (atr, htf_derived)))
