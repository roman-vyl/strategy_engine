from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.ema import EmaIndicatorEvaluator


@dataclass(frozen=True)
class LegacyFeature:
    feature_id: str
    kind: str
    source: str | None
    timeframe: str
    period: int | None
    base_feature_id: str | None = None
    multiplier: float | None = None


@dataclass(frozen=True)
class LegacyPlan:
    features: tuple[LegacyFeature, ...]


def _load_legacy_calculations(monkeypatch: pytest.MonkeyPatch):
    contracts = types.ModuleType("data_engine.contracts")
    contracts.pandas_freq_alias = lambda tf: {
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1D",
    }[tf]
    data_engine = types.ModuleType("data_engine")
    data_engine.contracts = contracts
    plan_module = types.ModuleType("research.strategies.ema_pullback.features.plan")
    plan_module.FeaturePlan = LegacyPlan
    monkeypatch.setitem(sys.modules, "data_engine", data_engine)
    monkeypatch.setitem(sys.modules, "data_engine.contracts", contracts)
    monkeypatch.setitem(
        sys.modules,
        "research.strategies.ema_pullback.features.plan",
        plan_module,
    )
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/features/calculations.py"
    )
    spec = importlib.util.spec_from_file_location("bbb_legacy_ema_calculations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(count: int = 36) -> tuple[pd.DataFrame, MarketFrame]:
    index = pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC")
    close = [100 + index_ * 0.7 + (index_ % 5) * 0.13 for index_ in range(count)]
    frame = pd.DataFrame(
        {
            "open": close,
            "high": [value + 1.2 for value in close],
            "low": [value - 0.8 for value in close],
            "close": close,
            "volume": [10 + index_ for index_ in range(count)],
        },
        index=index,
    )
    bars = tuple(
        MarketBar(
            open_time_ms=int(timestamp.timestamp() * 1000),
            open=Decimal(str(row.open)),
            high=Decimal(str(row.high)),
            low=Decimal(str(row.low)),
            close=Decimal(str(row.close)),
            volume=Decimal(str(row.volume)),
        )
        for timestamp, row in frame.iterrows()
    )
    start = bars[0].open_time_ms
    market = MarketFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(start, start + count * 300_000),
        bars,
        "golden-fixture",
    )
    return frame, market


@pytest.mark.parametrize("timeframe,period", [("base", 3), ("base", 11), ("1h", 2)])
def test_new_ema_matches_copied_bbb_implementation(
    monkeypatch: pytest.MonkeyPatch,
    timeframe: str,
    period: int,
) -> None:
    legacy = _load_legacy_calculations(monkeypatch)
    frame, market = _fixture()
    output_id = f"ema_close_{timeframe}_{period}"
    legacy_result = legacy.add_feature_columns_from_plan(
        frame,
        LegacyPlan((LegacyFeature(output_id, "ema", "close", timeframe, period),)),
    )[output_id]
    result = (
        EmaIndicatorEvaluator()
        .evaluate(
            market,
            IndicatorPlan(
                "1",
                (PlannedFeature(output_id, "ema", timeframe, "close", {"period": period}),),
            ),
        )
        .series[output_id]
    )
    actual = [None if value is None else float(value) for value in result]
    expected = [None if pd.isna(value) else float(value) for value in legacy_result]
    assert len(actual) == len(expected)
    for left, right in zip(actual, expected, strict=True):
        if right is None:
            assert left is None
        else:
            assert left == pytest.approx(right, rel=1e-14, abs=1e-14)
