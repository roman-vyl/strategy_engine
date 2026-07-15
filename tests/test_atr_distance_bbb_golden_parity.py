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
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator


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


def _load_legacy(monkeypatch: pytest.MonkeyPatch):
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
    spec = importlib.util.spec_from_file_location("bbb_legacy_atr_distance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(count: int = 72) -> tuple[pd.DataFrame, MarketFrame]:
    index = pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC")
    close = [100 + idx * 0.47 + (idx % 7) * 0.19 for idx in range(count)]
    frame = pd.DataFrame(
        {
            "open": [value - 0.2 for value in close],
            "high": [value + 1.1 + (idx % 3) * 0.1 for idx, value in enumerate(close)],
            "low": [value - 0.9 - (idx % 4) * 0.08 for idx, value in enumerate(close)],
            "close": close,
            "volume": [10 + idx for idx in range(count)],
        },
        index=index,
    )
    bars = tuple(
        MarketBar(
            int(timestamp.timestamp() * 1000),
            Decimal(str(row.open)),
            Decimal(str(row.high)),
            Decimal(str(row.low)),
            Decimal(str(row.close)),
            Decimal(str(row.volume)),
        )
        for timestamp, row in frame.iterrows()
    )
    start = bars[0].open_time_ms
    return frame, MarketFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(start, start + count * 300_000),
        bars,
        "golden-fixture",
    )


@pytest.mark.parametrize(
    "timeframe,period,multiplier",
    [("base", 3, 0.5), ("base", 14, 2.25), ("1h", 2, 1.75)],
)
def test_new_atr_distance_matches_copied_bbb(
    monkeypatch: pytest.MonkeyPatch,
    timeframe: str,
    period: int,
    multiplier: float,
) -> None:
    legacy = _load_legacy(monkeypatch)
    frame, market = _fixture()
    base_id = f"atr_{timeframe}_{period}"
    output_id = f"{base_id}_x"
    legacy_result = legacy.add_feature_columns_from_plan(
        frame,
        LegacyPlan(
            (
                LegacyFeature(base_id, "atr", "close", timeframe, period),
                LegacyFeature(
                    output_id,
                    "atr_distance",
                    None,
                    timeframe,
                    None,
                    base_id,
                    multiplier,
                ),
            )
        ),
    )[output_id]
    result = (
        RangeIndicatorEvaluator()
        .evaluate(
            market,
            IndicatorPlan(
                "1",
                (
                    PlannedFeature(
                        base_id,
                        "atr",
                        timeframe,
                        "close",
                        {"period": period},
                    ),
                    PlannedFeature(
                        output_id,
                        "atr_distance",
                        timeframe,
                        None,
                        {"multiplier": multiplier},
                        (base_id,),
                    ),
                ),
            ),
        )
        .series[output_id]
    )
    actual = [None if value is None else float(value) for value in result]
    expected = [None if pd.isna(value) else float(value) for value in legacy_result]
    for left, right in zip(actual, expected, strict=True):
        if right is None:
            assert left is None
        else:
            assert left == pytest.approx(right, rel=1e-14, abs=1e-14)
