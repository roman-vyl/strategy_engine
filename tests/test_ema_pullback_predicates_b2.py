"""B2 DI wave strength (OpenSpec `b2-di-wave-v1`): parsing, `touch: previous`,
`by_side`, `from_start` and `ratio.right_floor` against a loop written like the
research reference (previous-wave DI rise and area)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_a2 import _episode, _legs, _parse
from test_ema_pullback_predicates_band import _segment, _segment_args

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import (
    Operand,
    Ratio,
    segment_values,
)

_DI = {"kind": "di_plus", "timeframe": "base", "params": {"period": 14}}
_DI_MINUS = {"kind": "di_minus", "timeframe": "base", "params": {"period": 14}}


def _b2_fields(**fields: Any) -> dict[str, Any]:
    return {**_B2_BASE, **fields}


def _b2(**fields: Any) -> dict[str, Any]:
    return _segment(**_b2_fields(**fields))


_B2_BASE: dict[str, Any] = {
    "of": {"by_side": {"long": _DI, "short": _DI_MINUS}},
    "from": "origin",
    "to": "peak",
    "value": "from_start",
    "aggregate": "max",
}


# -- parsing ----------------------------------------------------------------------


def test_b2_fields_parse() -> None:
    segment = _parse({"segment": _b2(touch="previous")}).long.operand.segment
    assert segment.touch == "previous" and segment.value == "from_start"
    assert segment.series.by_side and segment.series.for_side("short").kind == "di_minus"
    current = _parse({"segment": _b2()}).long.operand.segment
    assert current.touch == "current"
    ratio = _parse(
        {"ratio": {"left": {"segment": _b2()}, "right": {"segment": _b2()}, "right_floor": 1e-6}}
    ).long.operand.ratio
    assert ratio.right_floor == 1e-6


@pytest.mark.parametrize(
    "fields",
    [
        {"touch": "next"},
        {"touch": "previous", "from": "peak", "to": "current"},
        {"touch": "previous", "from": "origin", "to": "current"},
        {"aggregate": "abs_sum"},
        {"aggregate": "top_abs_share", "top": 5, "window": {"last_n": 5}},
        {"value": "from_start", "span": 3},
        {"window": {"last_n": 10}},
        {"of": {"by_side": {"long": _DI}}},
        {"of": {"by_side": {"long": _DI, "short": _DI_MINUS, "both": _DI}}},
        {"of": {"by_side": {"long": _DI, "short": _DI_MINUS}, "difference": {}}},
    ],
)
def test_b2_invalid_fields_are_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"segment": _b2(**fields)})


@pytest.mark.parametrize("floor", ["x", True, float("nan"), float("inf")])
def test_right_floor_must_be_a_finite_number(floor: Any) -> None:
    with pytest.raises(InvalidRequestError):
        _parse(
            {
                "ratio": {
                    "left": {"segment": _b2()},
                    "right": {"segment": _b2()},
                    "right_floor": floor,
                }
            }
        )


# -- values against the research loop ------------------------------------------------


def _wave(line: np.ndarray, origin: int, peak: int) -> tuple[float, float]:
    window = line[origin : peak + 1]
    return float(window.max() - window[0]), float(window.mean() - window[0])


def _reference(episode: Any, line: np.ndarray) -> dict[str, np.ndarray]:
    """Per bar: rise and mean area of the current and the previous impulse."""

    names = ("rise", "area", "prev_rise", "prev_area")
    out = {name: np.full(len(line), np.nan) for name in names}
    touches = episode.touches
    for t in range(len(line)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if peak > t:
            continue
        out["rise"][t], out["area"][t] = _wave(line, origin, peak)
        number = int(episode.state["touch_number"][t])
        if number < 2:
            continue
        row = int(episode.first_row[int(episode.state["episode_id"][t])]) + number - 2
        previous = _wave(line, int(touches["origin_bar"][row]), int(touches["peak_bar"][row]))
        out["prev_rise"][t], out["prev_area"][t] = previous
    return out


def _segments(touch: str, aggregate: str) -> Any:
    return _segment_args(
        start="origin", end="peak", value="from_start", aggregate=aggregate, touch=touch
    )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize(("aggregate", "key"), [("max", "rise"), ("mean_per_bar", "area")])
def test_from_start_and_previous_touch_match_the_loop(seed: int, aggregate: str, key: str) -> None:
    episode, size = _episode(seed)
    rng = np.random.default_rng(seed + 100)
    line = 20.0 + np.cumsum(rng.normal(0, 1, size))
    expected = _reference(episode, line)
    now = segment_values(episode, line, _segments("current", aggregate))
    before = segment_values(episode, line, _segments("previous", aggregate))
    for t in range(size):
        legs = _legs(episode, t)
        if legs is not None and legs[1] > t:
            assert np.isnan(now[t])
            continue
        np.testing.assert_allclose(now[t], expected[key][t], atol=1e-9, equal_nan=True)
        np.testing.assert_allclose(before[t], expected["prev_" + key][t], atol=1e-9, equal_nan=True)
    assert np.isfinite(before).any() and np.isnan(before).any()


def test_sum_from_start_is_the_area_without_the_start_level() -> None:
    episode, size = _episode(2)
    line = 5.0 + np.cumsum(np.random.default_rng(1).normal(0, 1, size))
    total = segment_values(episode, line, _segments("current", "sum"))
    mean = segment_values(episode, line, _segments("current", "mean_per_bar"))
    for t in range(size):
        legs = _legs(episode, t)
        if legs is None or legs[1] > t:
            continue
        np.testing.assert_allclose(total[t], mean[t] * (legs[1] - legs[0] + 1), atol=1e-9)


def test_a_non_finite_value_in_the_wave_blanks_it_and_one_bar_gives_zero() -> None:
    episode, size = _episode(3)
    line = np.cumsum(np.ones(size))
    ok = segment_values(episode, line, _segments("current", "max"))
    t = int(np.flatnonzero(np.isfinite(ok))[-1])
    origin, peak, _ = _legs(episode, t)  # type: ignore[misc]
    broken = line.copy()
    broken[(origin + peak) // 2] = np.nan
    assert np.isnan(segment_values(episode, broken, _segments("current", "max"))[t])
    flat = segment_values(episode, np.full(size, 30.0), _segments("current", "max"))
    assert flat[t] == 0.0


def test_only_bars_up_to_t_are_read() -> None:
    episode, size = _episode(4)
    line = np.cumsum(np.random.default_rng(9).normal(0, 1, size))
    full = segment_values(episode, line, _segments("previous", "max"))
    for cut in (size // 3, size // 2):
        altered = line.copy()
        altered[cut + 1 :] += 50.0
        got = segment_values(episode, altered, _segments("previous", "max"))
        np.testing.assert_array_equal(got[: cut + 1], full[: cut + 1])


# -- ratio floor ----------------------------------------------------------------------


def test_right_floor_empties_small_zero_and_negative_denominators() -> None:
    from strategy_engine.strategies.ema_pullback.predicates import _ratio_operand

    class _Frame:
        time_ms = np.arange(1)

    def value(left: float, right: float, floor: float) -> float:
        ratio = Ratio(Operand(const=left), Operand(const=right), floor)
        return float(_ratio_operand(ratio, _Frame(), None, None, "long", None, "operand")[0])  # type: ignore[arg-type]

    for right in (2.0, 1e-6, 1e-7, 0.0, -1.0):
        assert np.isfinite(value(1.0, right, 0.0)) == (right > 0)
        assert np.isfinite(value(1.0, right, 1e-6)) == (right > 1e-6)
    assert value(-1.0, 2.0, 1e-6) == -0.5  # a numerator at or under zero is a value


# -- by_side and identity -------------------------------------------------------------


def test_identity_marks_touch_by_side_and_floor_only_when_set() -> None:
    from test_ema_pullback_predicates_a2 import _segment_identity

    from strategy_engine.domain.node_identity import node_spec
    from strategy_engine.strategies.ema_pullback.stack_episode import episode_identity_key

    def local(**fields: Any) -> Any:
        predicate, ids, resolve = _segment_identity(**fields)
        episode = node_spec("episode.ema_stack", version=1, params={"ref": "trend"}, side="long")
        identity = resolve(
            predicate, ids, "long", contexts={episode_identity_key("trend", "long"): episode}
        )
        return identity.nested[0]

    current = local(**_b2_fields())
    previous = local(**_b2_fields(touch="previous"))
    assert "touch" not in dict(current.params) and dict(previous.params)["touch"] == (
        "str",
        "previous",
    )
    assert dict(current.params)["by_side"] == ("bool", True)
    assert current != previous
    plain = local(value="level")
    assert "by_side" not in dict(plain.params) and plain != current
