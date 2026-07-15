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
    plan_module._adx_feature_id = lambda tf, period: f"adx_close_{tf}_{period}"
    plan_module._di_plus_feature_id = lambda tf, period: f"di_plus_close_{tf}_{period}"
    plan_module._di_minus_feature_id = lambda tf, period: f"di_minus_close_{tf}_{period}"
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
    spec = importlib.util.spec_from_file_location("bbb_legacy_adx_dmi_calculations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(count: int = 160) -> tuple[pd.DataFrame, MarketFrame]:
    index = pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC")
    close = [100 + idx * 0.21 + ((idx % 11) - 5) * 0.39 for idx in range(count)]
    frame = pd.DataFrame(
        {
            "open": [value - 0.15 for value in close],
            "high": [value + 0.8 + (idx % 4) * 0.1 for idx, value in enumerate(close)],
            "low": [value - 0.7 - (idx % 3) * 0.12 for idx, value in enumerate(close)],
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


@pytest.mark.parametrize("timeframe,period", [("base", 3), ("base", 14), ("1h", 3)])
def test_new_adx_dmi_matches_copied_bbb_implementation(
    monkeypatch: pytest.MonkeyPatch,
    timeframe: str,
    period: int,
) -> None:
    legacy = _load_legacy_calculations(monkeypatch)
    frame, market = _fixture()
    legacy_features = tuple(
        LegacyFeature(f"ignored_{kind}", kind, "close", timeframe, period)
        for kind in ("adx", "di_plus", "di_minus")
    )
    legacy_result = legacy.add_feature_columns_from_plan(frame, LegacyPlan(legacy_features))
    new_features = tuple(
        PlannedFeature(
            f"{kind}_{timeframe}_{period}",
            kind,
            timeframe,
            "close",
            {"period": period},
        )
        for kind in ("adx", "di_plus", "di_minus")
    )
    result = RangeIndicatorEvaluator().evaluate(
        market,
        IndicatorPlan("1", new_features),
    )
    legacy_names = {
        "adx": f"adx_close_{timeframe}_{period}",
        "di_plus": f"di_plus_close_{timeframe}_{period}",
        "di_minus": f"di_minus_close_{timeframe}_{period}",
    }
    for kind in ("adx", "di_plus", "di_minus"):
        actual = [
            None if value is None else float(value)
            for value in result.series[f"{kind}_{timeframe}_{period}"]
        ]
        expected = [
            None if pd.isna(value) else float(value) for value in legacy_result[legacy_names[kind]]
        ]
        for left, right in zip(actual, expected, strict=True):
            if right is None:
                assert left is None
            else:
                assert left == pytest.approx(right, rel=1e-14, abs=1e-14)
