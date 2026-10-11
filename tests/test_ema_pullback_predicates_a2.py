"""A2 shape aggregates on segments (OpenSpec `a2-shape-aggregates-v1`): parsing,
and every new field against a loop written like the research reference
(`a2_ideas_peek.py` lines 10-20)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from test_ema_pullback_predicates_band import _segment, _segment_args

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import (
    Eligibility,
    Segment,
    parse_predicate,
    segment_values,
)


def _parse(operand: dict[str, Any]) -> Any:
    return parse_predicate(
        {"kind": "range", "operand": operand, "min": 0.9, "max": None},
        "p",
        episode_refs=["trend"],
    )


# -- parsing ----------------------------------------------------------------------


def test_new_fields_parse() -> None:
    predicate = _parse(
        {
            "segment": _segment(
                value="change_over",
                span=3,
                aggregate="min",
                window={"last_n": 75},
                negate=True,
                eligibility={"legs_min_bars": 3, "window": 75, "impulse_positive": True},
            )
        }
    )
    segment = predicate.long.operand.segment
    assert segment.span == 3 and segment.aggregate == "min" and segment.negate
    assert segment.eligibility == Eligibility(3, 75, True)
    top = _parse(
        {"segment": _segment(value="change", aggregate="top_abs_sum", top=5, window={"last_n": 75})}
    ).long.operand.segment
    assert top.top == 5 and top.span is None and top.eligibility is None


@pytest.mark.parametrize(
    "fields",
    [
        {"value": "change_over"},  # span missing
        {"value": "change", "span": 3},  # span without change_over
        {"value": "change_over", "span": 0, "aggregate": "max"},
        {"value": "change_over", "span": True, "aggregate": "max"},
        {"value": "level", "aggregate": "max"},
        {"value": "level", "aggregate": "abs_sum"},
        {"value": "change_over", "span": 3, "aggregate": "sum"},
        {"value": "change_over", "span": 3, "aggregate": "mean_per_bar"},
        {"value": "change", "aggregate": "top_abs_sum", "window": {"last_n": 75}},  # top missing
        {"value": "change", "aggregate": "top_abs_sum", "top": 5},  # last_n missing
        {"value": "change", "aggregate": "top_abs_sum", "top": 0, "window": {"last_n": 5}},
        {"value": "change", "aggregate": "abs_sum", "top": 5},
        {"value": "change", "aggregate": "abs_sum", "eligibility": {"unknown": 1}},
        {"value": "change", "aggregate": "abs_sum", "eligibility": {"legs_min_bars": 0}},
        {"value": "change", "aggregate": "abs_sum", "eligibility": {"window": True}},
        {"value": "change", "aggregate": "abs_sum", "eligibility": {"impulse_positive": 1}},
        {
            "value": "change",
            "aggregate": "abs_sum",
            "eligibility": {"impulse_positive": True},  # needs window
        },
    ],
)
def test_invalid_fields_are_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"segment": _segment(**fields)})


# -- the research reference loop ----------------------------------------------------


def _episode(seed: int, cycles: int = 9, longest: int = 30) -> tuple[Any, int]:
    """An episode on bars with real legs: a rising impulse to a peak, a falling
    pullback, then a contact bar (`C`), repeated; flat anchor at 100."""

    rng = np.random.default_rng(seed)
    high, low, close = [102.0], [101.0], [101.5]
    for _ in range(cycles):
        up, down = int(rng.integers(2, longest)), int(rng.integers(2, longest))
        level = 102.0
        for _ in range(up):
            level += 0.5
            high.append(level + 0.4)
            low.append(level - 0.4)
            close.append(level)
        for i in range(down):
            level -= 0.9 * (level - 101.5) / max(down - i, 1) + 0.01
            high.append(level + 0.4)
            low.append(max(level - 0.4, 100.3))
            close.append(level)
        high.append(100.5)
        low.append(99.5)
        close.append(100.2)
    for _ in range(2):
        high.append(102.0)
        low.append(101.0)
        close.append(101.5)
    size = len(high)
    fast = [99.0] + [101.0] * (size - 1)
    from strategy_engine.strategies.ema_pullback.stack_episode import project_side

    episode = project_side(
        np.array(high),
        np.array(low),
        np.array(close),
        np.array(fast),
        np.full(size, 100.0),
        np.full(size, 99.0),
        _params_for(3),
        "long",
    )
    return episode, size


def _params_for(window: int) -> Any:
    from test_ema_pullback_stack_episode import _params

    return _params(window=window)


def _legs(episode: Any, t: int) -> tuple[int, int, int] | None:
    state, touches = episode.state, episode.touches
    number = state["touch_number"][t]
    if not np.isfinite(number) or number < 1:
        return None
    row = int(episode.first_row[int(state["episode_id"][t])]) + int(number) - 1
    return int(touches["origin_bar"][row]), int(touches["peak_bar"][row]), t


def _research(
    episode: Any, line: np.ndarray, *, window: int, short: int, k: int, top: int
) -> dict[str, np.ndarray]:
    """a2_ideas_peek.py lines 10-20 on a side-signed `line`."""

    d = np.diff(line, prepend=np.nan)
    out = {name: np.full(len(line), np.nan) for name in ("accel", "peak", "conc", "guard")}
    for t in range(len(line)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        impulse = np.arange(origin, peak + 1)
        pullback = np.arange(peak, t + 1)
        if len(impulse) < 3 or len(pullback) < 3:
            continue
        impulse, pullback = impulse[-window:], pullback[-window:]
        di, dr = d[impulse], d[pullback]
        if np.isnan(di).any() or np.isnan(dr).any() or di.sum() <= 0:
            continue
        out["guard"][t] = 1.0
        nr = -dr.sum() / len(dr)
        if nr > 0:
            out["accel"][t] = (-dr[-short:].sum() / len(dr[-short:])) / nr
        pi = np.convolve(di, np.ones(k), "valid").max()
        pr = (-np.convolve(dr, np.ones(k), "valid")).max()
        if pi > 0:
            out["peak"][t] = pr / pi
        a = np.abs(dr)
        total = a.sum()
        if total > 0:
            out["conc"][t] = np.sort(a)[-top:].sum() / total
    return out


ELIGIBILITY = lambda window: Eligibility(3, window, True)  # noqa: E731


def _blocks(window: int, short: int, k: int, top: int) -> dict[str, tuple[Segment, Segment]]:
    def seg(**fields: Any) -> Segment:
        return _segment_args(eligibility=ELIGIBILITY(window), **fields)

    pull = {"start": "peak", "end": "current", "last_n": window}
    return {
        "accel": (
            seg(start="peak", end="current", value="change", last_n=short, negate=True),
            seg(start="peak", end="current", value="change", last_n=window, negate=True),
        ),
        "peak": (
            seg(**pull, value="change_over", span=k, aggregate="min", negate=True),
            seg(
                start="origin",
                end="peak",
                last_n=window,
                value="change_over",
                span=k,
                aggregate="max",
            ),
        ),
        "conc": (
            seg(**pull, value="change", aggregate="top_abs_sum", top=top),
            seg(**pull, value="change", aggregate="abs_sum"),
        ),
    }


def _ratio(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    out = np.full(len(left), np.nan)
    valid = np.isfinite(left) & np.isfinite(right) & (right > 0)
    np.divide(left, right, out=out, where=valid)
    return out


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("window,short,k,top", [(75, 12, 3, 5), (6, 2, 3, 2), (4, 3, 2, 3)])
def test_branches_match_the_research_loop(
    seed: int, window: int, short: int, k: int, top: int
) -> None:
    episode, size = _episode(seed)
    rng = np.random.default_rng(100 + seed)
    line = np.cumsum(rng.normal(0.2, 1.0, size))
    expected = _research(episode, line, window=window, short=short, k=k, top=top)
    for name, (numerator, denominator) in _blocks(window, short, k, top).items():
        value = _ratio(
            segment_values(episode, line, numerator), segment_values(episode, line, denominator)
        )
        np.testing.assert_allclose(
            value, expected[name], rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=name
        )
    assert np.isfinite(expected["conc"]).sum() > 10, "shape must give values"


def test_values_below_zero_stay_values_and_denominators_do_not() -> None:
    episode, size = _episode(1)
    rng = np.random.default_rng(7)
    line = np.cumsum(rng.normal(0.0, 1.0, size))
    expected = _research(episode, line, window=6, short=2, k=3, top=2)
    accel = expected["accel"]
    peak = expected["peak"]
    assert (peak[np.isfinite(peak)] <= 0).any() or (accel[np.isfinite(accel)] <= 0).any()


def test_conc_is_one_on_a_window_shorter_than_top() -> None:
    episode, size = _episode(2)
    line = np.cumsum(np.random.default_rng(2).normal(0.3, 1.0, size))
    pull = {"start": "peak", "end": "current", "value": "change", "last_n": 75}
    top = segment_values(episode, line, _segment_args(aggregate="top_abs_sum", top=500, **pull))
    total = segment_values(episode, line, _segment_args(aggregate="abs_sum", **pull))
    assert np.isfinite(total).sum() > 10
    np.testing.assert_allclose(top, total, equal_nan=True)


def test_eligibility_is_shared_by_every_branch_and_blocks_short_legs() -> None:
    episode, size = _episode(3)
    line = np.cumsum(np.random.default_rng(11).normal(0.2, 1.0, size))
    expected = _research(episode, line, window=75, short=12, k=3, top=5)
    guard = np.isfinite(expected["guard"])
    for numerator, denominator in _blocks(75, 12, 3, 5).values():
        for segment in (numerator, denominator):
            got = segment_values(episode, line, segment)
            assert not np.isfinite(got[~guard]).any()


def test_a_non_finite_change_in_either_window_blanks_every_branch() -> None:
    episode, size = _episode(4)
    line = np.cumsum(np.random.default_rng(13).normal(0.2, 1.0, size))
    line[10] = np.nan
    expected = _research(episode, line, window=75, short=12, k=3, top=5)
    for name, (numerator, denominator) in _blocks(75, 12, 3, 5).items():
        value = _ratio(
            segment_values(episode, line, numerator), segment_values(episode, line, denominator)
        )
        np.testing.assert_allclose(value, expected[name], equal_nan=True, atol=1e-12)


def test_branches_use_only_bars_up_to_the_evaluated_bar() -> None:
    episode, size = _episode(5)
    rng = np.random.default_rng(17)
    line = np.cumsum(rng.normal(0.2, 1.0, size))
    for _, (numerator, denominator) in _blocks(75, 12, 3, 5).items():
        full = [segment_values(episode, line, s) for s in (numerator, denominator)]
        for cut in (20, 40):
            changed_line = line.copy()
            changed_line[cut + 1 :] = rng.normal(0, 100, len(line) - cut - 1)
            for before, segment in zip(full, (numerator, denominator), strict=True):
                after = segment_values(episode, changed_line, segment)
                np.testing.assert_array_equal(before[: cut + 1], after[: cut + 1])
