from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.adx_dmi import compute_adx_dmi
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.service.registries import IndicatorRegistry


def market_frame(count: int = 96) -> MarketFrame:
    step_ms = 300_000
    bars = tuple(
        MarketBar(
            open_time_ms=index * step_ms,
            open=Decimal(str(100 + index * 0.2)),
            high=Decimal(str(101 + index * 0.2 + (index % 4) * 0.3)),
            low=Decimal(str(99 + index * 0.2 - (index % 3) * 0.2)),
            close=Decimal(str(100 + index * 0.2 + ((index % 7) - 3) * 0.1)),
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


def feature(kind: str, *, timeframe: str = "base", period: object = 3) -> PlannedFeature:
    return PlannedFeature(
        output_id=f"{kind}_{timeframe}_{period}",
        kind=kind,
        timeframe=timeframe,
        source="close",
        parameters={"period": period},
    )


def test_registry_exposes_adx_and_directional_indices() -> None:
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
    assert registry.get_schema("adx")["calculation_group"] == "adx_dmi"


def test_adx_dmi_outputs_have_bbb_warmup_boundaries() -> None:
    result = RangeIndicatorEvaluator().evaluate(
        market_frame(),
        IndicatorPlan(
            "1",
            (
                feature("adx", period=3),
                feature("di_plus", period=3),
                feature("di_minus", period=3),
            ),
        ),
    )
    assert result.series["di_plus_base_3"][:3] == (None, None, None)
    assert result.series["di_plus_base_3"][3] is not None
    assert result.series["di_minus_base_3"][:3] == (None, None, None)
    assert result.series["adx_base_3"][:4] == (None,) * 4
    assert result.series["adx_base_3"][4] is not None
    assert result.validity["di_plus_base_3"].warmup_bars == 3
    assert result.validity["adx_base_3"].warmup_bars == 4


def test_htf_adx_dmi_uses_completed_bucket_alignment() -> None:
    result = RangeIndicatorEvaluator().evaluate(
        market_frame(120),
        IndicatorPlan(
            "1",
            (
                feature("adx", timeframe="1h", period=2),
                feature("di_plus", timeframe="1h", period=2),
                feature("di_minus", timeframe="1h", period=2),
            ),
        ),
    )
    assert result.series["di_plus_1h_2"][:36] == (None,) * 36
    assert result.series["di_plus_1h_2"][36] is not None
    assert result.series["adx_1h_2"][:36] == (None,) * 36
    assert result.series["adx_1h_2"][36] is not None


@pytest.mark.parametrize("period", [0, -1, True, 2.5, "3"])
def test_invalid_adx_dmi_period_is_rejected(period: object) -> None:
    with pytest.raises(InvalidRequestError):
        IndicatorRegistry().validate_feature(feature("adx", period=period))


def test_adx_dmi_rejects_source_extra_parameters_and_dependencies() -> None:
    registry = IndicatorRegistry()
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(PlannedFeature("x", "adx", "base", "high", {"period": 3}))
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "di_plus", "base", "close", {"period": 3, "x": 1})
        )
    with pytest.raises(InvalidRequestError):
        registry.validate_feature(
            PlannedFeature("x", "di_minus", "base", "close", {"period": 3}, ("y",))
        )


def test_wilder_group_computation_is_deterministic() -> None:
    frame = market_frame()
    import pandas as pd

    data = pd.DataFrame(
        {
            "high": [float(bar.high) for bar in frame.bars],
            "low": [float(bar.low) for bar in frame.bars],
            "close": [float(bar.close) for bar in frame.bars],
        }
    )
    first = compute_adx_dmi(data.high, data.low, data.close, period=14)
    second = compute_adx_dmi(data.high, data.low, data.close, period=14)
    for left, right in zip(first, second, strict=True):
        assert left.equals(right)
