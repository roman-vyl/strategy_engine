"""batch-computation-reuse group 2: shared range-invariant market arrays.

Proves, at the DataFrame/array level, that the shared `MarketArrays`
conversion is bit-identical to each former per-node Decimal -> float64
conversion (reproduced verbatim below as the oracle), and that one
evaluation request converts the range once rather than once per
variant/node.
"""

from __future__ import annotations

import json
import struct
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from parity.harness import market_fixture_bytes
from test_evaluate_strategy_range_batch import (
    SpyMarketData,
    _batch_request,
    _build,
    minimal_spec,
)

from strategy_engine.domain.errors import EvaluationInvariantError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.values import parse_decimal_text
from strategy_engine.indicators.contracts import FeatureFrame, IndicatorPlan
from strategy_engine.indicators.implementations.frame_ops import market_frame_to_dataframe
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.indicators.market_arrays import MarketArrays, frame_market_arrays
from strategy_engine.strategies.ema_pullback import exits, setups, triggers

_FIELDS = ("open", "high", "low", "close", "volume")


# -- oracles: the pre-change per-node conversions, verbatim ------------------


def _legacy_market_frame_to_dataframe(market_frame: MarketFrame) -> pd.DataFrame:
    index = pd.to_datetime(
        [bar.open_time_ms for bar in market_frame.bars],
        unit="ms",
        utc=True,
    )
    return pd.DataFrame(
        {
            "open": [float(bar.open) for bar in market_frame.bars],
            "high": [float(bar.high) for bar in market_frame.bars],
            "low": [float(bar.low) for bar in market_frame.bars],
            "close": [float(bar.close) for bar in market_frame.bars],
            "volume": [float(bar.volume) for bar in market_frame.bars],
        },
        index=index,
    )


def _legacy_market_values(bars: tuple[MarketBar, ...], field: str) -> tuple[float, ...]:
    return tuple(float(getattr(bar, field)) for bar in bars)


def _legacy_exit_frame_dataframe(frame: FeatureFrame) -> pd.DataFrame:
    index = pd.to_datetime(frame.time_ms, unit="ms", utc=True)
    data: dict[str, object] = {
        "open": [float(bar.open) for bar in frame.market_bars],
        "high": [float(bar.high) for bar in frame.market_bars],
        "low": [float(bar.low) for bar in frame.market_bars],
        "close": [float(bar.close) for bar in frame.market_bars],
        "volume": [float(bar.volume) for bar in frame.market_bars],
    }
    for output_id, values in frame.series.items():
        data[output_id] = [float("nan") if value is None else float(value) for value in values]
    return pd.DataFrame(data, index=index)


# -- helpers -------------------------------------------------------------------


def _fixture_market_frame() -> MarketFrame:
    payload = json.loads(market_fixture_bytes())
    bars = tuple(
        MarketBar(
            open_time_ms=candle["open_time_ms"],
            open=parse_decimal_text(candle["open"]),
            high=parse_decimal_text(candle["high"]),
            low=parse_decimal_text(candle["low"]),
            close=parse_decimal_text(candle["close"]),
            volume=parse_decimal_text(candle["volume"]),
        )
        for candle in payload["candles"]
    )
    return MarketFrame(
        MarketStream(payload["ticker"], payload["timeframe"]),
        TimeRange(payload["from_ms"], payload["to_ms"]),
        bars,
        payload["market_data_hash"],
    )


def _awkward_market_frame() -> MarketFrame:
    """Decimals chosen to stress float rounding (long mantissas, ties,
    subnormal-adjacent and huge magnitudes)."""

    texts = (
        "0.1",
        "0.30000000000000004",
        "123456789.123456789123456789",
        "1E-320",
        "1.7976931348623157E+308",
        "2.5",
        "0.000000000000000000000000123",
        "99999.99999999999999",
    )
    bars = tuple(
        MarketBar(
            index * 300_000,
            Decimal(texts[index % len(texts)]),
            Decimal(texts[(index + 1) % len(texts)]),
            Decimal(texts[(index + 2) % len(texts)]),
            Decimal(texts[(index + 3) % len(texts)]),
            Decimal(texts[(index + 4) % len(texts)]),
        )
        for index in range(24)
    )
    return MarketFrame(MarketStream("BTCUSDT.P", "5m"), TimeRange(0, 24 * 300_000), bars, "h")


def _assert_frames_bit_identical(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    assert list(actual.columns) == list(expected.columns)
    assert list(actual.dtypes) == list(expected.dtypes)
    assert actual.index.dtype == expected.index.dtype
    assert actual.index.freq == expected.index.freq
    assert actual.index.asi8.tobytes() == expected.index.asi8.tobytes()
    for column in expected.columns:
        assert actual[column].to_numpy().tobytes() == expected[column].to_numpy().tobytes(), column


def _float_bits(values: tuple[float, ...]) -> bytes:
    return b"".join(struct.pack("<d", value) for value in values)


# -- bit-identity of the shared representation ----------------------------------


@pytest.mark.parametrize("builder", [_fixture_market_frame, _awkward_market_frame])
def test_shared_dataframe_is_bit_identical_to_legacy_conversion(builder: object) -> None:
    market_frame = builder()  # type: ignore[operator]
    arrays = MarketArrays.from_market_frame(market_frame)
    expected = _legacy_market_frame_to_dataframe(market_frame)
    _assert_frames_bit_identical(arrays.dataframe(), expected)
    _assert_frames_bit_identical(market_frame_to_dataframe(market_frame), expected)
    assert arrays.time_ms == tuple(bar.open_time_ms for bar in market_frame.bars)


@pytest.mark.parametrize("builder", [_fixture_market_frame, _awkward_market_frame])
def test_shared_values_are_bit_identical_python_floats(builder: object) -> None:
    market_frame = builder()  # type: ignore[operator]
    arrays = MarketArrays.from_market_frame(market_frame)
    for field in _FIELDS:
        legacy = _legacy_market_values(market_frame.bars, field)
        shared = arrays.values(field)
        assert all(type(value) is float for value in shared)
        assert _float_bits(shared) == _float_bits(legacy)
        assert arrays.array(field).tobytes() == np.array(legacy, dtype=np.float64).tobytes()
        assert not arrays.array(field).flags.writeable


def test_each_conversion_runs_once_and_dataframes_are_never_shared() -> None:
    arrays = MarketArrays.from_market_frame(_awkward_market_frame())
    first, second = arrays.dataframe(), arrays.dataframe()
    assert arrays.values("close") is arrays.values("close")
    assert arrays.index() is arrays.index()
    assert first is not second
    for field in _FIELDS:
        assert not np.shares_memory(first[field].to_numpy(), arrays.array(field))
        assert not np.shares_memory(first[field].to_numpy(), second[field].to_numpy())


def test_exit_policy_frame_matches_legacy_with_and_without_attached_arrays() -> None:
    market_frame = _awkward_market_frame()
    native = RangeIndicatorEvaluator().evaluate_native(
        market_frame, IndicatorPlan(plan_version="v1", features=())
    )
    series = {
        "feature_a": tuple(None if i % 3 == 0 else float(i) / 7 for i in range(24)),
        "feature_b": tuple(float(i) * 1.1 for i in range(24)),
    }
    base = dict(
        market=native.market,
        requested_range=native.requested_range,
        time_ms=native.time_ms,
        series=series,
        validity={},
        plan_hash="p",
        market_data_hash="h",
        market_bars=market_frame.bars,
    )
    attached = FeatureFrame(**base, market_arrays=native.market_arrays)  # type: ignore[arg-type]
    detached = FeatureFrame(**base)  # type: ignore[arg-type]
    expected = _legacy_exit_frame_dataframe(detached)
    _assert_frames_bit_identical(exits._frame_dataframe(attached), expected)
    _assert_frames_bit_identical(exits._frame_dataframe(detached), expected)
    for field in ("close", "low", "high"):
        legacy_bits = _float_bits(_legacy_market_values(market_frame.bars, field))
        for module in (setups, triggers):
            assert _float_bits(module._market_values(attached, field)) == legacy_bits
            assert _float_bits(module._market_values(detached, field)) == legacy_bits
    assert frame_market_arrays(attached) is native.market_arrays


def test_empty_range_keeps_legacy_frame_shape() -> None:
    market_frame = MarketFrame(MarketStream("BTCUSDT.P", "5m"), TimeRange(0, 0), (), "h")
    _assert_frames_bit_identical(
        MarketArrays.from_market_frame(market_frame).dataframe(),
        _legacy_market_frame_to_dataframe(market_frame),
    )


# -- one conversion per evaluation request -------------------------------------


class _ConstructionSpy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.instances: list[MarketArrays] = []
        self.conversions: list[tuple[int, str]] = []
        original_init = MarketArrays.__init__
        original_values = MarketArrays.values
        spy = self

        def init(self: MarketArrays, *args: object, **kwargs: object) -> None:
            original_init(self, *args, **kwargs)  # type: ignore[arg-type]
            spy.instances.append(self)

        def values(self: MarketArrays, field: str) -> tuple[float, ...]:
            if field not in self._values:
                spy.conversions.append((id(self), field))
            return original_values(self, field)

        monkeypatch.setattr(MarketArrays, "__init__", init)
        monkeypatch.setattr(MarketArrays, "values", values)


def test_range_batch_converts_the_range_once_for_all_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _ConstructionSpy(monkeypatch)
    batch_eval, _ = _build(SpyMarketData())
    outcomes = tuple(batch_eval.execute(_batch_request(4)))
    assert all(outcome.error is None for outcome in outcomes)
    assert len(spy.instances) == 1
    assert len(spy.conversions) == len(set(spy.conversions))


def test_single_spec_converts_the_range_once_per_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from strategy_engine.strategies.contracts import LiveStrategySpec, StrategyRangeRequest

    spy = _ConstructionSpy(monkeypatch)
    _, strategy_eval = _build(SpyMarketData())
    request = StrategyRangeRequest(
        strategy=LiveStrategySpec("ema_pullback", minimal_spec()),
        market=MarketStream("BTCUSDT.P", "5m"),
        time_range=TimeRange(0, 3_600_000),
    )
    strategy_eval.execute_projection(request)
    assert len(spy.instances) == 1
    assert len(spy.conversions) == len(set(spy.conversions))


def test_arrays_from_a_different_frame_are_rejected() -> None:
    market_frame = _awkward_market_frame()
    other = MarketArrays.from_market_frame(_awkward_market_frame())
    with pytest.raises(EvaluationInvariantError):
        RangeIndicatorEvaluator().evaluate_native(
            market_frame,
            IndicatorPlan(plan_version="v1", features=()),
            market_arrays=other,
        )
