"""A3 leg speed operand (OpenSpec `a3-leg-speed-ratio-v1`): parsing, the impulse
`|Pp - Sp| / (P - S* + 1)` and the pullback `|Pp - close[t]| / (t - P + 1)` against a
loop written like the research reference (`altvals.py` `a3`), missing cases and no
look-ahead."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.leg_speed import leg_speed_values


def _operand(**fields: Any) -> dict[str, Any]:
    return {"leg_speed": {"episode": "trend", "leg": "pullback", **fields}}


def reference(episode: Any, close: np.ndarray, leg: str) -> np.ndarray:
    out = np.full(len(close), math.nan)
    for t in range(len(close)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])])
        row += int(episode.state["touch_number"][t]) - 1
        pp = float(episode.touches["peak_price"][row])
        sp = float(episode.touches["origin_price"][row])
        if leg == "impulse":
            value = abs(pp - sp) / (peak - origin + 1)
        else:
            value = abs(pp - close[t]) / (t - peak + 1)
        if math.isfinite(value):
            out[t] = value
    return out


def research_a3(episode: Any, close: np.ndarray) -> np.ndarray:
    """`altvals.py`: `(dR / nR) / (Hs / nI)` when `Hs > 0`."""

    pullback, impulse = reference(episode, close, "pullback"), reference(episode, close, "impulse")
    out = np.full(len(close), math.nan)
    ok = np.isfinite(pullback) & np.isfinite(impulse) & (impulse > 0)
    out[ok] = pullback[ok] / impulse[ok]
    return out


def test_leg_speed_parses_as_a_range_and_ratio_operand() -> None:
    assert _parse(_operand()).long.operand.leg_speed.leg == "pullback"
    ratio = {"ratio": {"left": _operand(), "right": _operand(leg="impulse")}}
    assert _parse(ratio).long.operand.ratio.right.leg_speed.leg == "impulse"


@pytest.mark.parametrize(
    "fields", [{"leg": "current"}, {"episode": "other"}, {"episode": ""}, {"extra": 1}]
)
def test_malformed_leg_speed_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_operand(**fields))


@pytest.mark.parametrize("missing", ["episode", "leg"])
def test_required_fields(missing: str) -> None:
    operand = _operand()
    del operand["leg_speed"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_leg_speed_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
@pytest.mark.parametrize("side", ["long", "short"])
def test_leg_speed_matches_the_loop(seed: int, leg: str, side: str) -> None:
    episode, _, (_, _, close) = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    got = leg_speed_values(episode, close, leg)
    np.testing.assert_allclose(got, reference(episode, close, leg), rtol=1e-12, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable


def test_zero_impulse_height_gives_zero_speed() -> None:
    episode, _, (_, _, close) = _episode_bars(5)
    touches = dict(episode.touches)
    touches["origin_price"] = np.array(touches["peak_price"], dtype=float)
    flat = dataclasses.replace(episode, touches=touches)
    impulse = leg_speed_values(flat, close, "impulse")
    assert (impulse[np.isfinite(impulse)] == 0).all() and np.isfinite(impulse).any()
    assert np.isnan(research_a3(flat, close)).all()


def test_non_finite_close_is_missing() -> None:
    episode, _, (_, _, close) = _episode_bars(4)
    base = leg_speed_values(episode, close, "pullback")
    t = int(np.flatnonzero(np.isfinite(base))[5])
    bad = close.copy()
    bad[t] = math.nan
    got = leg_speed_values(episode, bad, "pullback")
    assert math.isnan(got[t])
    keep = np.arange(len(close)) != t
    np.testing.assert_array_equal(got[keep], base[keep])


def test_no_look_ahead() -> None:
    episode, size, (_, _, close) = _episode_bars(2)
    for leg in ("impulse", "pullback"):
        full = leg_speed_values(episode, close, leg)
        for cut in (size // 3, size // 2, size - 5):
            changed = close.copy()
            changed[cut + 1 :] = 1e9
            got = leg_speed_values(episode, changed, leg)
            np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


# -- leg bars (OpenSpec `a4-leg-bars-ratio-v1`) --------------------------------------


def bars_reference(episode: Any, size: int, leg: str) -> np.ndarray:
    out = np.full(size, math.nan)
    for t in range(size):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if origin <= peak <= t:
            out[t] = (peak - origin + 1) if leg == "impulse" else (t - peak + 1)
    return out


def research_a4(episode: Any, close: np.ndarray) -> np.ndarray:
    """`altvals.py`: `nR / nI` when `Hs > 0`."""

    size = len(close)
    pullback, impulse = (
        bars_reference(episode, size, "pullback"),
        bars_reference(episode, size, "impulse"),
    )
    height = reference(episode, close, "impulse")
    out = np.full(size, math.nan)
    ok = np.isfinite(pullback) & np.isfinite(impulse) & (height > 0)
    out[ok] = pullback[ok] / impulse[ok]
    return out


def test_leg_bars_parses_and_rejects() -> None:
    operand = {"leg_bars": {"episode": "trend", "leg": "impulse"}}
    assert _parse(operand).long.operand.leg_bars.leg == "impulse"
    for bad in ({"leg": "current"}, {"extra": 1}, {"episode": "other"}):
        with pytest.raises(InvalidRequestError):
            _parse({"leg_bars": {"episode": "trend", "leg": "pullback", **bad}})
    with pytest.raises(InvalidRequestError):
        _parse({"leg_bars": {"episode": "trend"}})


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("leg", ["impulse", "pullback"])
@pytest.mark.parametrize("side", ["long", "short"])
def test_leg_bars_matches_the_loop(seed: int, leg: str, side: str) -> None:
    from strategy_engine.strategies.ema_pullback.leg_speed import leg_bars_values

    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    got = leg_bars_values(episode, leg)
    np.testing.assert_array_equal(got, bars_reference(episode, size, leg))
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable
