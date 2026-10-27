"""Absolute value operand (OpenSpec `ki-abs-operand-v1`): parsing, placement and the
bar-by-bar absolute value of the inner operand on both sides."""

from __future__ import annotations

import dataclasses
import math
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_leg_change import reference
from test_ema_pullback_predicates_a2 import _episode_bars, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import _absolute_operand


def _change(**fields: Any) -> dict[str, Any]:
    return {"leg_change": {"episode": "trend", "leg": "impulse", "field": "close", **fields}}


def test_abs_parses_alone_and_inside_a_ratio() -> None:
    operand = _parse({"abs": _change()}).long.operand
    assert operand.absolute.leg_change.field == "close"
    ratio = {"ratio": {"left": _change(field="open_interest"), "right": {"abs": _change()}}}
    assert _parse(ratio).long.operand.ratio.right.absolute.leg_change.leg == "impulse"


@pytest.mark.parametrize(
    "inner",
    [
        {"const": 1.0},
        {"abs": _change()},
        {"ratio": {"left": _change(), "right": _change()}},
        {"leg_change": {"episode": "trend", "leg": "both", "field": "close"}},
    ],
)
def test_malformed_abs_is_rejected(inner: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"abs": inner})


def test_abs_is_not_a_change_operand() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "change", "operand": {"abs": _change()}, "lookback": 3, "op": ">", "value": 0},
            "p",
            episode_refs=["trend"],
        )


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("side", ["long", "short"])
def test_abs_of_a_leg_change_is_its_absolute_value(seed: int, side: str) -> None:
    episode, size, _ = _episode_bars(seed)
    episode = dataclasses.replace(episode, side=side)
    close = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 0.01, size)))
    frame = SimpleNamespace(
        time_ms=np.arange(size),
        market_arrays=SimpleNamespace(array=lambda name: close),
    )
    bundle = SimpleNamespace(episodes=SimpleNamespace(side=lambda ref, s: episode))
    inner = _parse(_change()).long.operand
    got = _absolute_operand(inner, frame, None, None, side, bundle, "operand")  # type: ignore[arg-type]
    expected = np.abs(reference(episode, close, "impulse"))
    np.testing.assert_allclose(got, expected, rtol=0, equal_nan=True)
    signed = reference(episode, close, "impulse")
    assert (signed < 0).any() and (signed > 0).any() and np.isnan(got).any()
    assert not got.flags.writeable and not math.isnan(float(np.nanmin(got)))
