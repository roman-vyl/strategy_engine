"""B3 impulse ATR operand (OpenSpec `b3-impulse-atr-v1`): parsing, the value
`|Pp - Sp| / atr[P]` against a loop written like the research reference (`altvals.py`
`b3h`), missing cases and no look-ahead."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode_bars, _legs, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.impulse_atr import impulse_atr_values

ATR = {"kind": "atr", "params": {"period": 48}}


def _operand(**fields: Any) -> dict[str, Any]:
    return {"impulse_atr": {"episode": "trend", "atr": ATR, **fields}}


def reference(episode: Any, atr: np.ndarray) -> np.ndarray:
    out = np.full(len(atr), math.nan)
    for t in range(len(atr)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])])
        row += int(episode.state["touch_number"][t]) - 1
        height = abs(
            float(episode.touches["peak_price"][row]) - float(episode.touches["origin_price"][row])
        )
        if math.isfinite(atr[peak]) and atr[peak] > 0:
            out[t] = height / atr[peak]
    return out


def _atr(size: int, seed: int) -> np.ndarray:
    atr = np.random.default_rng(seed).uniform(0.2, 1.5, size)
    atr[:5] = math.nan  # start of history
    return atr


def test_impulse_atr_parses_as_a_range_and_ratio_operand() -> None:
    operand = _parse(_operand()).long.operand.impulse_atr
    assert operand.episode == "trend" and operand.atr.kind == "atr"
    assert operand.atr.parameters["period"] == 48
    ratio = {"ratio": {"left": _operand(), "right": {"const": 2.0}}}
    assert _parse(ratio).long.operand.ratio.left.impulse_atr.atr.kind == "atr"


@pytest.mark.parametrize(
    "fields",
    [
        {"atr": {"kind": "atr_wilder", "params": {"period": 14}}},
        {"atr": {"kind": "atr", "timeframe": "15m", "params": {"period": 48}}},
        {"episode": "other"},
        {"extra": 1},
    ],
)
def test_malformed_impulse_atr_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(_operand(**fields))


@pytest.mark.parametrize("missing", ["episode", "atr"])
def test_required_fields(missing: str) -> None:
    operand = _operand()
    del operand["impulse_atr"][missing]
    with pytest.raises(InvalidRequestError):
        _parse(operand)


def test_impulse_atr_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": _operand(), "lookback": 3, "op": ">", "value": 0.0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
def test_impulse_atr_matches_the_loop(seed: int, side: str) -> None:
    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    atr = _atr(size, seed)
    got = impulse_atr_values(episode, atr)
    np.testing.assert_allclose(got, reference(episode, atr), rtol=1e-12, equal_nan=True)
    assert np.isfinite(got).sum() > 20 and np.isnan(got).any() and not got.flags.writeable


def test_zero_height_is_zero_and_missing_atr_is_missing() -> None:
    episode, size, _ = _episode_bars(5)
    touches = dict(episode.touches)
    touches["origin_price"] = np.array(touches["peak_price"], dtype=float)
    flat = dataclasses.replace(episode, touches=touches)
    got = impulse_atr_values(flat, _atr(size, 5))
    assert np.isfinite(got).any() and (got[np.isfinite(got)] == 0).all()
    assert np.isnan(impulse_atr_values(episode, np.full(size, math.nan))).all()
    assert np.isnan(impulse_atr_values(episode, np.zeros(size))).all()


def test_no_look_ahead() -> None:
    episode, size, _ = _episode_bars(2)
    atr = _atr(size, 2)
    full = impulse_atr_values(episode, atr)
    for cut in (size // 3, size // 2, size - 5):
        changed = atr.copy()
        changed[cut + 1 :] = 1e9
        got = impulse_atr_values(episode, changed)
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])
