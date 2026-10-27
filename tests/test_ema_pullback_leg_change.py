"""Leg change operand (OpenSpec `o1-leg-change-v1`): parsing, the percent change
`100 * (x[end] / x[begin] - 1)` of a base-bar field over the impulse `[S*, P]`, the
pullback `[P, t]` and the previous impulse against a loop written like the research
reference (`review/oi5/engine_rule/feat.py` O1), missing cases, open interest read
from the market arrays and no look-ahead."""

from __future__ import annotations

import dataclasses
import math
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar
from strategy_engine.indicators.market_arrays import MarketArrays
from strategy_engine.strategies.ema_pullback.leg_change import leg_change_values
from strategy_engine.strategies.ema_pullback.predicates import LegChange, _leg_change_operand


def _operand(**fields: Any) -> dict[str, Any]:
    return {
        "leg_change": {"episode": "trend", "leg": "impulse", "field": "open_interest", **fields}
    }


def _change(x: np.ndarray, a: int, z: int) -> float:
    first, last = x[a], x[z]
    if not (math.isfinite(first) and math.isfinite(last)) or first <= 0:
        return math.nan
    return 100 * (last / first - 1)


def _row(episode: Any, t: int) -> int:
    state = episode.state
    return int(episode.first_row[int(state["episode_id"][t])]) + int(state["touch_number"][t]) - 1


def reference(episode: Any, x: np.ndarray, leg: str, touch: str = "current") -> np.ndarray:
    out = np.full(len(x), math.nan)
    for t in range(len(x)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        if touch == "previous":
            if episode.state["touch_number"][t] < 2:
                continue
            row = _row(episode, t) - 1
            s0, p0 = episode.touches["origin_bar"][row], episode.touches["peak_bar"][row]
            if not (np.isfinite(s0) and np.isfinite(p0) and s0 <= p0):
                continue
            out[t] = _change(x, int(s0), int(p0))
        else:
            out[t] = _change(x, origin, peak) if leg == "impulse" else _change(x, peak, t)
    return out


def _series(size: int, seed: int) -> np.ndarray:
    return 70_000 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 0.01, size)))


def test_leg_change_parses_as_a_range_and_ratio_operand() -> None:
    operand = _parse(_operand()).long.operand.leg_change
    assert operand == LegChange("trend", "impulse", "open_interest", "current")
    ratio = {"ratio": {"left": _operand(), "right": _operand(field="close")}}
    assert _parse(ratio).long.operand.ratio.right.leg_change.field == "close"
    previous = _parse(_operand(touch="previous")).long.operand.leg_change
    assert previous.touch == "previous"


@pytest.mark.parametrize(
    "fields",
    [
        {"leg": "both"},
        {"episode": "other"},
        {"extra": 1},
        {"field": "volume"},
        {"touch": "next"},
        {"touch": "previous", "leg": "pullback"},
    ],
)
def test_malformed_leg_change_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_operand(**fields))


@pytest.mark.parametrize("missing", ["episode", "leg", "field"])
def test_required_fields(missing: str) -> None:
    operand = _operand()
    del operand["leg_change"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_leg_change_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize(
    ("leg", "touch"), [("impulse", "current"), ("pullback", "current"), ("impulse", "previous")]
)
def test_leg_change_matches_the_loop(seed: int, side: str, leg: str, touch: str) -> None:
    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    x = _series(size, seed)
    got = leg_change_values(episode, x, leg, touch)
    np.testing.assert_allclose(got, reference(episode, x, leg, touch), rtol=1e-12, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable


def test_falling_open_interest_over_the_impulse() -> None:
    episode, size, _ = _episode_bars(4)
    t = next(t for t in range(size) if (lg := _legs(episode, t)) and lg[0] < lg[1] < t)
    s, p, _ = _legs(episode, t)  # type: ignore[misc]
    x = np.full(size, 1000.0)
    x[s], x[p] = 1000.0, 940.0
    assert leg_change_values(episode, x, "impulse")[t] == pytest.approx(-6.0)
    assert leg_change_values(episode, x, "pullback")[t] == pytest.approx(100 * (1000 / 940 - 1))


def test_missing_or_non_positive_end_values_are_missing() -> None:
    episode, size, _ = _episode_bars(3)
    t = next(t for t in range(size) if (lg := _legs(episode, t)) and lg[0] < lg[1] < t)
    s, p, _ = _legs(episode, t)  # type: ignore[misc]
    x = _series(size, 3)
    gap = x.copy()
    gap[p] = math.nan
    assert math.isnan(leg_change_values(episode, gap, "impulse")[t])
    zero = x.copy()
    zero[s] = 0.0
    assert math.isnan(leg_change_values(episode, zero, "impulse")[t])
    inside = x.copy()
    inside[s + 1 : p] = math.nan  # only the two ends are read
    assert (
        leg_change_values(episode, inside, "impulse")[t]
        == leg_change_values(episode, x, "impulse")[t]
    )


def test_no_look_ahead() -> None:
    episode, size, _ = _episode_bars(2)
    x = _series(size, 2)
    for leg, touch in (("impulse", "current"), ("pullback", "current"), ("impulse", "previous")):
        full = leg_change_values(episode, x, leg, touch)
        for cut in (size // 3, size // 2, size - 5):
            changed = x.copy()
            changed[cut + 1 :] = 1e9
            got = leg_change_values(episode, changed, leg, touch)
            np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


def test_operand_reads_open_interest_from_the_market_arrays() -> None:
    episode, size, _ = _episode_bars(5)
    x = _series(size, 5).round(3)
    gap = size // 2
    bars = tuple(
        MarketBar(
            index * 300_000,
            Decimal("1"),
            Decimal("2"),
            Decimal("0.5"),
            Decimal("1.5"),
            Decimal("10"),
            None if index == gap else Decimal(repr(float(x[index]))),
        )
        for index in range(size)
    )
    frame = SimpleNamespace(market_arrays=MarketArrays(tuple(b.open_time_ms for b in bars), bars))
    bundle = SimpleNamespace(episodes=SimpleNamespace(side=lambda ref, side: episode))
    expected_series = x.copy()
    expected_series[gap] = math.nan
    operand = LegChange("trend", "impulse", "open_interest")
    got = _leg_change_operand(operand, frame, "long", bundle)  # type: ignore[arg-type]
    np.testing.assert_allclose(
        got, reference(episode, expected_series, "impulse"), rtol=1e-12, equal_nan=True
    )
