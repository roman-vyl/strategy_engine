"""Open interest as a leg field: `leg_mean`, `leg_sum` and `leg_top_mean` read
`open_interest` from the shared market arrays exactly like `volume`; a bar
without open interest makes its leg missing."""

from __future__ import annotations

import math
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar
from strategy_engine.indicators.market_arrays import MarketArrays
from strategy_engine.strategies.ema_pullback.leg_means import (
    leg_mean_values,
    leg_sum_values,
    leg_top_mean_values,
)
from strategy_engine.strategies.ema_pullback.predicates import (
    LegMean,
    LegSum,
    LegTopMean,
    _leg_mean_operand,
    _leg_sum_operand,
    _leg_top_mean_operand,
)

_OPERANDS = {
    "leg_mean": {},
    "leg_sum": {},
    "leg_top_mean": {"share": 0.1},
}


@pytest.mark.parametrize("kind", sorted(_OPERANDS))
def test_open_interest_field_parses(kind: str) -> None:
    payload = {"episode": "trend", "leg": "impulse", "field": "open_interest", **_OPERANDS[kind]}
    operand = getattr(_parse({kind: payload}).long.operand, kind)
    assert operand.field == "open_interest"


@pytest.mark.parametrize("kind", sorted(_OPERANDS))
def test_unknown_market_field_is_still_rejected(kind: str) -> None:
    payload = {"episode": "trend", "leg": "impulse", "field": "turnover", **_OPERANDS[kind]}
    with pytest.raises(InvalidRequestError):
        _parse({kind: payload})


def _frame_and_bundle(seed: int, gap: int | None) -> tuple[Any, Any, np.ndarray, Any]:
    episode, size = _episode(seed)
    rng = np.random.default_rng(seed + 70)
    open_interest = rng.uniform(50_000.0, 90_000.0, size).round(3)
    volume = rng.uniform(1.0, 50.0, size).round(3)
    bars = tuple(
        MarketBar(
            index * 300_000,
            Decimal("1"),
            Decimal("2"),
            Decimal("0.5"),
            Decimal("1.5"),
            Decimal(repr(float(volume[index]))),
            None if index == gap else Decimal(repr(float(open_interest[index]))),
        )
        for index in range(size)
    )
    arrays = MarketArrays(tuple(bar.open_time_ms for bar in bars), bars)
    frame = SimpleNamespace(market_arrays=arrays)
    bundle = SimpleNamespace(episodes=SimpleNamespace(side=lambda ref, side: episode))
    expected = open_interest.copy()
    if gap is not None:
        expected[gap] = math.nan
    return frame, bundle, expected, episode


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
def test_operands_read_open_interest_like_volume(seed: int, leg: str) -> None:
    frame, bundle, series, episode = _frame_and_bundle(seed, gap=None)
    got_mean = _leg_mean_operand(LegMean("trend", leg, "open_interest"), frame, "long", bundle)
    got_sum = _leg_sum_operand(LegSum("trend", leg, "open_interest"), frame, "long", bundle)
    got_top = _leg_top_mean_operand(
        LegTopMean("trend", leg, "open_interest", 0.25), frame, "long", bundle
    )
    np.testing.assert_array_equal(got_mean, leg_mean_values(episode, series, leg))
    np.testing.assert_array_equal(got_sum, leg_sum_values(episode, series, leg))
    np.testing.assert_array_equal(got_top, leg_top_mean_values(episode, series, leg, 0.25))
    assert np.isfinite(got_mean).any()
    volume_mean = _leg_mean_operand(LegMean("trend", leg, "volume"), frame, "long", bundle)
    assert not np.array_equal(got_mean, volume_mean, equal_nan=True)


def test_a_bar_without_open_interest_makes_its_leg_missing() -> None:
    frame, bundle, _, episode = _frame_and_bundle(1, gap=None)
    full = _leg_mean_operand(LegMean("trend", "impulse", "open_interest"), frame, "long", bundle)
    t = int(np.flatnonzero(np.isfinite(full))[3])
    _, gap, _ = _legs(episode, t) or (0, 0, 0)
    frame, bundle, _, _ = _frame_and_bundle(1, gap=gap)
    for operand, call in (
        (LegMean("trend", "impulse", "open_interest"), _leg_mean_operand),
        (LegSum("trend", "impulse", "open_interest"), _leg_sum_operand),
        (LegTopMean("trend", "impulse", "open_interest", 0.1), _leg_top_mean_operand),
    ):
        assert math.isnan(call(operand, frame, "long", bundle)[t])
