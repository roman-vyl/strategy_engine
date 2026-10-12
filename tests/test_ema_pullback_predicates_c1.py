"""C1 counter-trade DI pullback wave (OpenSpec `c1-di-pullback-wave-v1`): the segment end
`touch` on a previous touch, parsing and values against a loop written like the research
reference (counter-DI rise and area of the pullback P..t against the previous P..T)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse
from test_ema_pullback_predicates_b2 import _wave
from test_ema_pullback_predicates_band import _segment, _segment_args

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import segment_values

_DI_MINUS = {"kind": "di_minus", "timeframe": "base", "params": {"period": 14}}
_DI_PLUS = {"kind": "di_plus", "timeframe": "base", "params": {"period": 14}}


def _c1_fields(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "of": {"by_side": {"long": _DI_MINUS, "short": _DI_PLUS}},
        "from": "peak",
        "to": "touch",
        "value": "from_start",
        "aggregate": "max",
        "touch": "previous",
    }
    return {**base, **fields}


def test_touch_end_parses_on_the_previous_touch() -> None:
    segment = _parse({"segment": _segment(**_c1_fields())}).long.operand.segment
    assert (segment.start, segment.end, segment.touch) == ("peak", "touch", "previous")
    assert segment.series.for_side("long").kind == "di_minus"
    assert segment.series.for_side("short").kind == "di_plus"


@pytest.mark.parametrize(
    "fields",
    [
        {"touch": "current"},  # the touch end belongs to the previous touch
        {"from": "origin"},
        {"from": "origin", "to": "touch", "touch": "previous"},
        {"to": "current"},  # previous pullback must end at its touch bar
        {"from": "peak", "to": "touch", "window": {"last_n": 5}},
    ],
)
def test_invalid_touch_end_is_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"segment": _segment(**_c1_fields(**fields))})


def _reference(episode: Any, line: np.ndarray) -> dict[str, np.ndarray]:
    names = ("rise", "area", "prev_rise", "prev_area")
    out = {name: np.full(len(line), np.nan) for name in names}
    touches = episode.touches
    for t in range(len(line)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        _, peak, _ = legs
        if peak > t:
            continue
        out["rise"][t], out["area"][t] = _wave(line, peak, t)
        number = int(episode.state["touch_number"][t])
        if number < 2:
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])]) + number - 2
        previous = _wave(line, int(touches["peak_bar"][row]), int(touches["touch_bar"][row]))
        out["prev_rise"][t], out["prev_area"][t] = previous
    return out


def _pair(aggregate: str) -> tuple[Any, Any]:
    now = _segment_args(start="peak", end="current", value="from_start", aggregate=aggregate)
    before = _segment_args(
        start="peak", end="touch", value="from_start", aggregate=aggregate, touch="previous"
    )
    return now, before


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize(("aggregate", "key"), [("max", "rise"), ("mean_per_bar", "area")])
def test_pullback_waves_match_the_loop(seed: int, aggregate: str, key: str) -> None:
    episode, size = _episode(seed)
    line = 20.0 + np.cumsum(np.random.default_rng(seed + 300).normal(0, 1, size))
    expected = _reference(episode, line)
    now_segment, before_segment = _pair(aggregate)
    now = segment_values(episode, line, now_segment)
    before = segment_values(episode, line, before_segment)
    np.testing.assert_allclose(now, expected[key], atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(before, expected["prev_" + key], atol=1e-9, equal_nan=True)
    assert np.isfinite(before).any() and np.isnan(before).any() and np.isfinite(now).any()


def test_previous_pullback_reads_only_bars_up_to_its_touch() -> None:
    episode, size = _episode(4)
    line = np.cumsum(np.random.default_rng(9).normal(0, 1, size))
    _, before_segment = _pair("max")
    full = segment_values(episode, line, before_segment)
    for cut in (size // 3, size // 2):
        altered = line.copy()
        altered[cut + 1 :] += 50.0
        got = segment_values(episode, altered, before_segment)
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])
