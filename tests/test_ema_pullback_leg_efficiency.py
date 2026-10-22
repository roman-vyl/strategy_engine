"""A5 leg efficiency operand (OpenSpec `a5-leg-efficiency-ratio-v1`): parsing, the
Kaufman efficiency of the impulse `[S*, P]` and the pullback `[P, t]` closes against a
loop written like the research reference (`altvals.py` `er`), missing cases and no
look-ahead."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.leg_efficiency import leg_efficiency_values


def _operand(**fields: Any) -> dict[str, Any]:
    return {"leg_efficiency": {"episode": "trend", "leg": "pullback", **fields}}


def _er(close: np.ndarray, a: int, z: int) -> float:
    if z <= a:
        return math.nan
    total = sum(abs(close[k] - close[k - 1]) for k in range(a + 1, z + 1))
    value = abs(close[z] - close[a]) / total if total > 0 else math.nan
    return value if math.isfinite(value) else math.nan


def reference(episode: Any, close: np.ndarray, leg: str) -> np.ndarray:
    out = np.full(len(close), math.nan)
    for t in range(len(close)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        out[t] = _er(close, origin, peak) if leg == "impulse" else _er(close, peak, t)
    return out


def research_a5(episode: Any, close: np.ndarray) -> np.ndarray:
    """`review/a5ex/ratio_grid.py`: `ER(P, t) / ER(S*, P)` where `ER(S*, P) > 0`."""

    pullback, impulse = reference(episode, close, "pullback"), reference(episode, close, "impulse")
    out = np.full(len(close), math.nan)
    ok = np.isfinite(pullback) & np.isfinite(impulse) & (impulse > 0)
    out[ok] = pullback[ok] / impulse[ok]
    return out


def _close(size: int, seed: int) -> np.ndarray:
    return 100 + np.cumsum(np.random.default_rng(seed).normal(0, 1, size))


def test_leg_efficiency_parses_as_a_range_and_ratio_operand() -> None:
    assert _parse(_operand()).long.operand.leg_efficiency.leg == "pullback"
    ratio = {"ratio": {"left": _operand(), "right": _operand(leg="impulse")}}
    assert _parse(ratio).long.operand.ratio.right.leg_efficiency.leg == "impulse"


@pytest.mark.parametrize("fields", [{"leg": "both"}, {"episode": "other"}, {"extra": 1}])
def test_malformed_leg_efficiency_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_operand(**fields))


@pytest.mark.parametrize("missing", ["episode", "leg"])
def test_required_fields(missing: str) -> None:
    operand = _operand()
    del operand["leg_efficiency"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_leg_efficiency_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
def test_leg_efficiency_matches_the_loop(seed: int, side: str, leg: str) -> None:
    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    close = _close(size, seed)
    got = leg_efficiency_values(episode, close, leg)
    np.testing.assert_allclose(got, reference(episode, close, leg), rtol=1e-12, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable


def test_straight_pullback_crooked_impulse() -> None:
    episode, size, _ = _episode_bars(4)
    close = _close(size, 4)
    t = next(
        t
        for t in range(size)
        if (lg := _legs(episode, t)) is not None and lg[0] + 3 <= lg[1] and lg[1] + 2 <= t
    )
    s, p, _ = _legs(episode, t)  # type: ignore[misc]
    close[s : p + 1] = 100.0
    close[p - 3 : p + 1] = [100, 103, 101, 104]
    close[p : t + 1] = np.linspace(104, 100, t - p + 1)
    impulse = leg_efficiency_values(episode, close, "impulse")[t]
    pullback = leg_efficiency_values(episode, close, "pullback")[t]
    assert impulse == pytest.approx(0.5) and pullback == pytest.approx(1.0)
    assert pullback / impulse == pytest.approx(2.0)


def _with_row(episode: Any, row: int, **columns: int) -> Any:
    touches = {key: np.array(value, copy=True) for key, value in episode.touches.items()}
    for key, value in columns.items():
        touches[key][row] = value
    return dataclasses.replace(episode, touches=touches)


def test_one_bar_leg_flat_closes_and_nan_are_missing() -> None:
    episode, size, _ = _episode_bars(3)
    close = _close(size, 3)
    t = next(t for t in range(size) if _legs(episode, t) is not None)
    row = int(episode.first_row[int(episode.state["episode_id"][t])])
    row += int(episode.state["touch_number"][t]) - 1
    origin = int(episode.touches["origin_bar"][row])
    one_bar_impulse = _with_row(episode, row, peak_bar=origin)
    assert math.isnan(leg_efficiency_values(one_bar_impulse, close, "impulse")[t])
    at_peak = _with_row(episode, row, peak_bar=t, origin_bar=min(origin, t))
    assert math.isnan(leg_efficiency_values(at_peak, close, "pullback")[t])
    assert np.isfinite(leg_efficiency_values(at_peak, close, "impulse")[t]) or origin >= t
    assert np.isnan(leg_efficiency_values(episode, np.full(size, 5.0), "impulse")).all()
    close[size // 2] = math.nan
    got = leg_efficiency_values(episode, close, "pullback")
    assert np.isfinite(got).any()
    np.testing.assert_allclose(got, reference(episode, close, "pullback"), equal_nan=True)


def test_no_look_ahead() -> None:
    episode, size, _ = _episode_bars(2)
    close = _close(size, 2)
    full = leg_efficiency_values(episode, close, "pullback")
    for cut in (size // 3, size // 2, size - 5):
        changed = close.copy()
        changed[cut + 1 :] = 1e9
        got = leg_efficiency_values(episode, changed, "pullback")
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])
