from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.values import (
    canonical_json_hash,
    normalized_decimal_text,
    parse_decimal_text,
)
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.strategies.contracts import StrategySpecEnvelope


def test_market_stream_requires_canonical_identity() -> None:
    assert MarketStream("BTCUSDT.P", "5m").ticker == "BTCUSDT.P"
    with pytest.raises(InvalidRequestError):
        MarketStream("BTC/USDT", "5m")


def test_range_is_half_open_and_aligned() -> None:
    TimeRange(0, 600_000).validate_alignment("5m")
    with pytest.raises(InvalidRequestError):
        TimeRange(1, 600_000).validate_alignment("5m")
    with pytest.raises(InvalidRequestError):
        TimeRange(600_000, 600_000).validate_alignment("5m")


def test_decimal_text_never_requires_float() -> None:
    assert parse_decimal_text("68450.100") == Decimal("68450.100")
    assert normalized_decimal_text(Decimal("68450.100")) == "68450.1"
    with pytest.raises(InvalidRequestError):
        parse_decimal_text("NaN")


def test_plan_and_strategy_hashes_are_deterministic() -> None:
    first = IndicatorPlan(
        "1",
        (
            PlannedFeature(
                output_id="ema_5m_200",
                kind="ema",
                timeframe="5m",
                source="close",
                parameters={"period": 200},
            ),
        ),
    )
    second = IndicatorPlan(
        "1",
        (
            PlannedFeature(
                output_id="ema_5m_200",
                kind="ema",
                timeframe="5m",
                source="close",
                parameters={"period": 200},
            ),
        ),
    )
    assert first.plan_hash == second.plan_hash
    assert canonical_json_hash({"b": 1, "a": 2}) == canonical_json_hash({"a": 2, "b": 1})

    spec = StrategySpecEnvelope("ema_pullback", "v1", "run-a", {"b": 1, "a": 2})
    same_semantics = StrategySpecEnvelope("ema_pullback", "v1", "run-b", {"a": 2, "b": 1})
    assert spec.config_hash == same_semantics.config_hash
