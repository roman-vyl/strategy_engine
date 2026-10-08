"""EMA stack episode projection (OpenSpec `ema-stack-episode-v1`, tasks
1.2-1.5): every touch rule on hand-built bars, the short mirror, wave
geometry, censoring, truncation invariance and the two approved drawings."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.stack_episode import (
    EpisodeParams,
    EpisodeRef,
    SideEpisode,
    episode_operand_values,
    parse_episode_ref,
    parse_episode_section,
    project_side,
    side_to_wire,
)
from strategy_engine.strategies.live_calculation.indicator_requirements import ema_warmup_bars

A = 100.0


def _params(window: int = 3, break_bars: int | None = None, slow_period: int = 1) -> EpisodeParams:
    # slow_period 1 -> a one-bar warm-up: only an episode on bar 0 is censored.
    return EpisodeParams(
        fast_period=1,
        anchor_period=1,
        slow_period=slow_period,
        window_bars=window,
        break_bars=window if break_bars is None else break_bars,
        history_bars=100,
    )


# Bar codes against a flat anchor at 100: U wholly above, C contact closing
# above, c contact closing below, D wholly below, X stack order broken (bar
# otherwise above), Y stack order broken and wholly below.
_SHAPES = {
    "U": (102.0, 101.0, 101.5),
    "C": (100.5, 99.5, 100.2),
    "c": (100.5, 99.5, 99.8),
    "D": (99.0, 98.0, 98.5),
    "X": (102.0, 101.0, 101.5),
    "Y": (99.0, 98.0, 98.5),
}


def _bars(codes: str) -> dict[str, np.ndarray]:
    high, low, close, fast = [], [], [], []
    for code in codes.replace(" ", ""):
        h, lo, c = _SHAPES[code]
        high.append(h)
        low.append(lo)
        close.append(c)
        fast.append(99.0 if code in "XY" else 101.0)
    size = len(high)
    return {
        "high": np.array(high),
        "low": np.array(low),
        "close": np.array(close),
        "fast": np.array(fast),
        "anchor": np.full(size, A),
        "slow": np.full(size, 99.0),
    }


def _project(codes: str, side: str = "long", **kwargs: Any) -> SideEpisode:
    bars = _bars(codes)
    return project_side(
        bars["high"],
        bars["low"],
        bars["close"],
        bars["fast"],
        bars["anchor"],
        bars["slow"],
        _params(**kwargs),
        side,
    )


def _wire(episode: SideEpisode) -> dict[str, Any]:
    return side_to_wire(episode, tuple(range(len(episode.state["active"]))))


def _bars_of(field: str, episode: SideEpisode) -> list[int]:
    return [int(i) for i in np.flatnonzero(episode.state[field] == 1.0)]


def _value(episode: SideEpisode, raw: dict[str, Any]) -> np.ndarray:
    return episode_operand_values(episode, parse_episode_ref(raw, "operand", None))


# -- boundaries ----------------------------------------------------------------


def test_episode_starts_on_order_and_bar_zero_episode_is_censored() -> None:
    episode = _project("UUUCU")
    assert episode.state["censored"].tolist() == [1.0] * 5
    assert math.isnan(episode.state["touch_number"][3])
    later = _project("XUUCU")
    assert _bars_of("episode_start", later) == [1]
    assert later.state["touch_number"].tolist()[1:] == [0.0, 0.0, 1.0, 1.0]
    assert later.state["active"].tolist() == [0.0, 1.0, 1.0, 1.0, 1.0]


def test_short_violation_keeps_the_episode() -> None:
    episode = _project("XUUCUUUUXXXUUCU", window=3)
    assert _bars_of("stack_break", episode) == []
    assert set(episode.state["episode_id"][1:].tolist()) == {1.0}
    assert episode.state["touch_number"][-1] == 2.0


def test_long_violation_ends_the_episode() -> None:
    episode = _project("XUUCUUUUXXXXUU", window=3)
    assert _bars_of("stack_break", episode) == [11]
    assert episode.state["active"][11] == 1.0
    assert episode.state["active"][12] == 1.0  # a new episode starts on the next held bar
    assert episode.state["episode_id"][12] == 2.0
    assert episode.state["touch_number"][12] == 0.0
    ended = _project("XUUCUUUUXXXXXX", window=3)
    assert ended.state["active"][12:].tolist() == [0.0, 0.0]
    assert np.isnan(ended.state["touch_number"][12:]).all()


# -- touch zones -----------------------------------------------------------------


def test_only_an_approach_from_above_opens_a_zone() -> None:
    # Contacts right after the start bar (above) count; a contact bar after
    # a contact bar does not open another zone.
    episode = _project("XUCCUUUUUCU", window=2)
    assert _bars_of("touch_start", episode) == [2, 9]
    assert _bars_of("zone_end", episode) == [6]


def test_saw_is_one_zone() -> None:
    episode = _project("XUCUUCUDDCUUUU", window=3)
    assert _bars_of("touch_start", episode) == [2]
    assert _bars_of("zone_end", episode) == [13]
    zones = _wire(episode)["zones"]
    assert len(zones) == 1
    assert zones[0]["start"]["bar"] == 2 and zones[0]["end"]["bar"] == 9


def test_below_bars_do_not_extend_the_zone_timer() -> None:
    # Last contact on bar c=2, bars 3..5 below (j=3 <= n), bar 6 above with
    # j + 1 = 4 > n = 3: the zone ends on bar 6, its range on bar 2.
    episode = _project("XUCDDDUUU", window=3)
    assert _bars_of("zone_end", episode) == [6]
    assert _bars_of("false_break_start", episode) == []
    zone = _wire(episode)["zones"][0]
    assert zone["end"]["bar"] == 2
    assert zone["known_at"]["bar"] == 6


def test_below_run_longer_than_window_is_a_false_break_of_the_same_zone() -> None:
    episode = _project("XUCDDDDcCUUCU", window=3)
    assert _bars_of("false_break_start", episode) == [6]
    assert _bars_of("comeback", episode) == [8]
    assert _bars_of("touch_start", episode) == [2, 11]
    wire = _wire(episode)
    false_break = wire["false_breaks"][0]
    assert false_break["number"] == 1
    assert (false_break["start"]["bar"], false_break["end"]["bar"]) == (3, 8)
    assert false_break["outcome"] == "comeback"
    assert false_break["depth"] == pytest.approx(99.5 - 98.0)
    assert wire["zones"][0]["end"]["bar"] == 2
    assert wire["zones"][0]["has_false_break"] is True
    assert episode.state["false_breaks"][-1] == 1.0
    assert episode.state["in_false_break"][6:8].tolist() == [1.0, 1.0]


def test_comeback_is_not_a_touch() -> None:
    # After the comeback the next bars stay in contact: no zone opens until a
    # bar wholly above is followed by a bar reaching the anchor.
    episode = _project("XUCDDDDCCCCUCU", window=3)
    assert _bars_of("comeback", episode) == [7]
    assert _bars_of("touch_start", episode) == [2, 12]
    assert episode.state["touch_number"][11] == 1.0
    assert episode.state["touch_number"][12] == 2.0


def test_no_zone_ceiling() -> None:
    codes = "XUC" + "DC" * 40 + "UUUU"
    episode = _project(codes, window=3)
    assert _bars_of("touch_start", episode) == [2]
    zone = _wire(episode)["zones"][0]
    assert zone["end"]["bar"] == 2 + 80
    assert zone["known_at"]["bar"] == 2 + 80 + 4


def test_false_break_then_stack_break() -> None:
    episode = _project("XUCDDDDYYYY", window=3)
    assert _bars_of("stack_break", episode) == [10]
    assert episode.state["touch_number"][10] == 1.0
    assert episode.state["in_zone"][10] == 0.0
    assert episode.state["in_false_break"][10] == 0.0
    assert episode.state["away"][10] == 0.0
    false_break = _wire(episode)["false_breaks"][0]
    assert false_break["outcome"] == "stack_break"
    assert false_break["final"] is True
    assert false_break["known_at"]["bar"] == 10


def test_open_zone_becomes_final_on_the_stack_break() -> None:
    episode = _project("XUCCXXXX", window=3)
    zone = _wire(episode)["zones"][0]
    assert zone["final"] is True
    assert zone["known_at"]["bar"] == 7
    assert zone["end"]["bar"] == 3


# -- waves -------------------------------------------------------------------------


def _priced(rows: list[tuple[float, float, float]], fast: float = 101.0) -> SideEpisode:
    high = np.array([row[0] for row in rows])
    low = np.array([row[1] for row in rows])
    close = np.array([row[2] for row in rows])
    size = len(rows)
    fast_series = np.full(size, fast)
    fast_series[0] = 99.0
    return project_side(
        high,
        low,
        close,
        fast_series,
        np.full(size, A),
        np.full(size, 99.0),
        _params(window=2),
        "long",
    )


def test_wave_origin_inside_a_false_break_and_peak_after_it() -> None:
    rows = [
        (102, 101, 101.5),  # 0 X
        (106, 103, 105),  # 1 start
        (108, 105, 107),  # 2
        (100.5, 99.6, 100.2),  # 3 touch 1 (zone low 99.6)
        (99.0, 97.0, 98),  # 4 below
        (98.5, 95.0, 96),  # 5 below
        (99.0, 96.0, 98),  # 6 below -> false break (run 3 > 2)
        (101.0, 98.0, 100.5),  # 7 comeback
        (103, 101, 102),  # 8
        (112, 104, 111),  # 9 peak
        (109, 103, 104),  # 10
        (101.5, 99.8, 101),  # 11 touch 2
    ]
    episode = _priced(rows)
    assert _bars_of("touch_start", episode) == [3, 11]
    waves = _wire(episode)["waves"]
    wave2 = next(item for item in waves if item["number"] == 2)
    assert wave2["origin"]["bar"] == 5 and wave2["origin_price"] == 95.0
    assert wave2["peak"]["bar"] == 9 and wave2["peak_price"] == 112.0
    assert wave2["touch"]["bar"] == 11 and wave2["touch_price"] == 99.8
    false_break = _wire(episode)["false_breaks"][0]
    assert false_break["depth"] == pytest.approx(99.6 - 95.0)
    up = _value(episode, {"ref": "e", "entity": "up_leg", "index": 0, "field": "range"})
    assert up[11] == pytest.approx(112.0 - 95.0)
    down = _value(episode, {"ref": "e", "entity": "down_leg", "index": 0, "field": "bars"})
    assert down[11] == 3.0  # bars 9..11


def test_peak_before_the_low_is_ignored() -> None:
    rows = [
        (102, 101, 101.5),  # 0 X
        (120, 104, 118),  # 1 start: highest high of the interval, before the low
        (105, 102, 103),  # 2
        (100.5, 99.5, 100.2),  # 3 touch 1
        (104, 101, 103),  # 4
        (110, 102, 109),  # 5 peak after the low
        (100.4, 99.9, 100.1),  # 6 contact
        (104, 101, 103),  # 7
        (104, 101, 103),  # 8
        (104, 101, 103),  # 9 zone ends (9 - 6 > 2)
        (115, 106, 114),  # 10 peak of wave 2
        (100.8, 99.7, 100.5),  # 11 touch 2
    ]
    episode = _priced(rows)
    assert _bars_of("touch_start", episode) == [3, 11]
    wave2 = next(item for item in _wire(episode)["waves"] if item["number"] == 2)
    assert wave2["origin"]["bar"] == 3  # lowest low after touch 1 (the touch bar itself)
    assert wave2["peak"]["bar"] == 10
    wave1 = next(item for item in _wire(episode)["waves"] if item["number"] == 1)
    assert wave1["origin"]["bar"] <= wave1["peak"]["bar"] <= wave1["touch"]["bar"]


def test_forming_wave_runs_to_the_current_bar() -> None:
    episode = _project("XUCUUUUUU", window=2)
    bars = _value(episode, {"ref": "e", "entity": "down_leg", "index": "forming", "field": "bars"})
    final = _value(episode, {"ref": "e", "entity": "wave", "index": "forming", "field": "final"})
    assert final[2:].tolist() == [0.0] * 7
    assert bars[8] >= 1.0
    origin = _value(
        episode, {"ref": "e", "entity": "wave", "index": "forming", "field": "start_bars_ago"}
    )
    assert origin[8] == 6.0  # origin is the touch bar 2 (lowest low since it)


# -- operand reads -----------------------------------------------------------------


def test_index_resolution_and_missing_values() -> None:
    episode = _project("XUCUUUCUUUCU", window=2)
    assert _bars_of("touch_start", episode) == [2, 6, 10]
    number = _value(episode, {"ref": "e", "field": "touch_number"})
    assert number[11] == 3.0
    start_current = _value(
        episode, {"ref": "e", "entity": "zone", "index": "current", "field": "start_bars_ago"}
    )
    start_previous = _value(
        episode, {"ref": "e", "entity": "zone", "index": "previous", "field": "start_bars_ago"}
    )
    start_first = _value(
        episode, {"ref": "e", "entity": "zone", "index": 1, "field": "start_bars_ago"}
    )
    assert start_current[11] == 1.0
    assert start_previous[11] == 5.0
    assert start_first[11] == 9.0
    assert math.isnan(start_previous[7]) is False and start_previous[7] == 5.0
    assert math.isnan(start_previous[3])  # only one zone yet
    too_far = _value(episode, {"ref": "e", "entity": "zone", "index": -5, "field": "bars"})
    assert np.isnan(too_far).all()
    fifth = _value(episode, {"ref": "e", "entity": "zone", "index": 5, "field": "bars"})
    assert np.isnan(fifth).all()
    no_break = _value(episode, {"ref": "e", "entity": "false_break", "index": 0, "field": "depth"})
    assert np.isnan(no_break).all()


def test_open_zone_values_are_as_of_each_bar() -> None:
    episode = _project("XUCCCUUUU", window=2)
    end_ago = _value(episode, {"ref": "e", "entity": "zone", "index": 0, "field": "end_bars_ago"})
    final = _value(episode, {"ref": "e", "entity": "zone", "index": 0, "field": "final"})
    assert end_ago[2:5].tolist() == [0.0, 0.0, 0.0]
    assert end_ago[6] == 2.0
    assert final[2:8].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]


# -- short mirror ---------------------------------------------------------------------


def test_short_side_mirrors_the_long_side() -> None:
    bars = _bars("XUCDDDDcCUUCUUUU")
    mirrored = {
        "high": 200.0 - bars["low"],
        "low": 200.0 - bars["high"],
        "close": 200.0 - bars["close"],
        "fast": 200.0 - bars["fast"],
        "anchor": 200.0 - bars["anchor"],
        "slow": 200.0 - bars["slow"],
    }
    params = _params(window=3)
    long = project_side(*(bars[key] for key in _ORDER), params, "long")
    short = project_side(*(mirrored[key] for key in _ORDER), params, "short")
    for key in long.state:
        np.testing.assert_array_equal(long.state[key], short.state[key])
    long_wire, short_wire = _wire(long), _wire(short)
    for long_zone, short_zone in zip(long_wire["zones"], short_wire["zones"], strict=True):
        assert short_zone["high"] == pytest.approx(200.0 - long_zone["low"])
        assert short_zone["low"] == pytest.approx(200.0 - long_zone["high"])
    for long_fb, short_fb in zip(
        long_wire["false_breaks"], short_wire["false_breaks"], strict=True
    ):
        assert short_fb["depth"] == pytest.approx(long_fb["depth"])
    leg = {"ref": "e", "entity": "up_leg", "index": 0, "field": "range"}
    np.testing.assert_allclose(_value(long, leg), _value(short, leg), equal_nan=True)


_ORDER = ("high", "low", "close", "fast", "anchor", "slow")


# -- censoring and truncation ---------------------------------------------------------


def _random_bars(size: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.4, size))
    high = close + rng.uniform(0.05, 0.6, size)
    low = close - rng.uniform(0.05, 0.6, size)

    def ema(values: np.ndarray, period: int) -> np.ndarray:
        alpha = 2.0 / (period + 1)
        out = np.empty_like(values)
        out[0] = values[0]
        for i in range(1, len(values)):
            out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
        return out

    return {
        "high": high,
        "low": low,
        "close": close,
        "fast": ema(close, 10),
        "anchor": ema(close, 25),
        "slow": ema(close, 60),
    }


def test_censoring_counts_the_slow_ema_warm_up() -> None:
    bars = _random_bars(3000, 3)
    params = EpisodeParams(10, 25, 60, 6, 6, 1000)
    episode = project_side(*(bars[key] for key in _ORDER), params, "long")
    warm_up = ema_warmup_bars(60)
    assert warm_up == 277
    censored_ids = {row["episode_id"] for row in episode.episodes if row["censored"]}
    assert censored_ids
    for row in episode.episodes:
        assert row["censored"] == (row["start_bar"] < warm_up)
    censored = episode.state["censored"] == 1.0
    assert np.isnan(episode.state["touch_number"][censored]).all()
    assert all(zone["episode_id"] not in censored_ids for zone in _wire(episode)["zones"])


@pytest.mark.parametrize("side", ["long", "short"])
def test_truncation_invariance(side: str) -> None:
    bars = _random_bars(2500, 11)
    params = EpisodeParams(10, 25, 60, 6, 6, 1000)
    full = project_side(*(bars[key] for key in _ORDER), params, side)
    operands = [
        {"ref": "e", "field": "touch_number"},
        {"ref": "e", "field": "in_false_break"},
        {"ref": "e", "entity": "zone", "index": 0, "field": "low"},
        {"ref": "e", "entity": "zone", "index": -1, "field": "range"},
        {"ref": "e", "entity": "false_break", "index": 0, "field": "depth"},
        {"ref": "e", "entity": "up_leg", "index": -1, "field": "range"},
        {"ref": "e", "entity": "down_leg", "index": "forming", "field": "bars"},
        {"ref": "e", "entity": "wave", "index": "forming", "field": "origin_price"},
    ]
    for cut in (700, 1300, 1999):
        part = project_side(*(bars[key][:cut] for key in _ORDER), params, side)
        for key in full.state:
            np.testing.assert_array_equal(full.state[key][:cut], part.state[key])
        for raw in operands:
            np.testing.assert_array_equal(_value(full, raw)[:cut], _value(part, raw))


# -- approved drawings (task 1.5) -------------------------------------------------------


def _lerp_closes(keypoints: list[tuple[int, float]], size: int) -> list[float]:
    out = []
    for t in range(size):
        k = 0
        while k < len(keypoints) - 1 and keypoints[k + 1][0] < t:
            k += 1
        t0, v0 = keypoints[k]
        t1, v1 = keypoints[min(k + 1, len(keypoints) - 1)]
        out.append(v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0))
    return out


def _drawing(
    keypoints: list[tuple[int, float]], size: int, seed: int, fast_gap: Any, slow_gap: Any
) -> dict[str, np.ndarray]:
    offsets = _lerp_closes(keypoints, size)
    state = seed

    def rnd() -> float:
        nonlocal state
        state = (state * 16807) % 2147483647
        return state / 2147483647

    rows: dict[str, list[float]] = {key: [] for key in _ORDER}
    previous_close = 0.0
    for t in range(size):
        e = 100 + 0.05 * t
        c = e + offsets[t]
        o = previous_close if t else c - 0.3
        rows["high"].append(max(o, c) + 0.15 + 0.35 * rnd())
        rows["low"].append(min(o, c) - 0.15 - 0.35 * rnd())
        rows["close"].append(c)
        rows["anchor"].append(e)
        rows["fast"].append(e + fast_gap(t))
        rows["slow"].append(e + slow_gap(t))
        previous_close = c
    return {key: np.array(values) for key, values in rows.items()}


def _slow_gap(cap: float) -> Any:
    return lambda t: 0.4 - 0.08 * t if t < 8 else -min(0.24 + 0.12 * (t - 8), cap)


def test_drawing_comeback_episode() -> None:
    """The owner-approved v6 drawing (touches 1-3, a false break, a
    comeback with no number, a later approach as touch 4, then a false
    break ended by the stack break)."""

    keypoints = [
        (0, -1.2), (4, -0.4), (8, 0.8), (14, 3.2), (22, 7.6), (26, 7.0), (33, 1.4), (34, 0.15),
        (36, 2.4), (44, 6.6), (48, 7.4), (56, 1.6), (57, 0.2), (58, 0.9), (59, 0.3), (60, -0.6),
        (61, -0.9), (62, -0.4), (63, 0.5), (64, 1.3), (66, 1.0), (67, 1.6), (72, 4.8), (80, 8.2),
        (84, 7.5), (90, 1.5), (91, 0.5), (92, -0.6), (94, -1.6), (98, -2.4), (101, -1.9),
        (103, -1.0), (104, -0.2), (105, 0.6), (106, 1.6), (110, 4.3), (113, 3.8), (116, 1.3),
        (117, 0.15), (119, 2.2), (126, 6.5), (130, 6.8), (136, 1.4), (137, 0.5), (138, -0.4),
        (140, -1.6), (146, -3.0), (152, -3.8), (160, -4.6), (168, -5.2),
    ]

    def fast_gap(t: int) -> float:
        if t < 8:
            return -0.6 + 0.075 * t
        if t < 140:
            return min(0.1 + 0.25 * (t - 8), 3.2) - (0.25 * (t - 130) if t > 130 else 0.0)
        return 0.95 - 0.32 * (t - 140)

    bars = _drawing(keypoints, 169, 7, fast_gap, _slow_gap(2.4))
    episode = project_side(*(bars[key] for key in _ORDER), _params(window=6), "long")
    assert _bars_of("episode_start", episode) == [8]
    assert _bars_of("touch_start", episode) == [34, 57, 92, 117, 138]
    assert _bars_of("false_break_start", episode) == [99, 146]
    assert _bars_of("comeback", episode) == [105]
    assert _bars_of("stack_break", episode) == [149]
    wire = _wire(episode)
    assert [(z["start"]["bar"], z["end"]["bar"]) for z in wire["zones"]] == [
        (34, 35), (57, 63), (92, 92), (117, 118), (138, 139),
    ]
    assert [
        (f["number"], f["start"]["bar"], f["end"]["bar"], f["outcome"])
        for f in wire["false_breaks"]
    ] == [(3, 93, 105, "comeback"), (5, 140, 149, "stack_break")]
    forming = [w for w in wire["waves"] if not w["final"]]
    assert len(forming) == 1 and forming[0]["number"] == 6
    assert episode.state["touch_number"][149] == 5.0


def test_drawing_wave_origin_in_false_break() -> None:
    """The owner-approved wave drawing: zone 2 has a false break, wave 3
    starts on that false break's low."""

    keypoints = [
        (0, -1.2), (4, -0.4), (8, 0.8), (14, 3.2), (22, 7.6), (26, 7.0), (33, 1.4), (34, 0.15),
        (35, 0.5), (37, 2.4), (46, 7.2), (50, 8.0), (56, 1.6), (57, 0.2), (58, 0.9), (59, 0.3),
        (60, -0.6), (61, -0.9), (62, -0.4), (63, 0.4), (64, 1.6), (66, 2.4), (67, 1.8), (68, 0.3),
        (69, -0.8), (70, -1.5), (73, -2.6), (76, -3.8), (79, -3.0), (82, -1.4), (83, -0.3),
        (84, 0.7), (86, 2.2), (92, 6.0), (98, 8.6), (101, 8.0), (107, 1.5), (108, 0.15),
        (109, 0.6), (111, 2.6), (118, 6.4), (121, 7.0), (124, 5.6), (129, 1.2), (130, 0.1),
    ]

    def fast_gap(t: int) -> float:
        return -0.6 + 0.075 * t if t < 8 else min(0.1 + 0.25 * (t - 8), 3.4)

    bars = _drawing(keypoints, 131, 11, fast_gap, _slow_gap(2.6))
    episode = project_side(*(bars[key] for key in _ORDER), _params(window=6), "long")
    assert _bars_of("touch_start", episode) == [34, 57, 108, 130]
    wire = _wire(episode)
    assert [(z["start"]["bar"], z["end"]["bar"]) for z in wire["zones"]] == [
        (34, 35), (57, 69), (108, 109), (130, 130),
    ]
    (false_break,) = wire["false_breaks"]
    assert (false_break["number"], false_break["start"]["bar"], false_break["end"]["bar"]) == (
        2, 70, 84,
    )
    assert false_break["low"] == pytest.approx(99.527314, abs=1e-6)
    waves = [(w["number"], w["origin"]["bar"], w["peak"]["bar"], w["touch"]["bar"])
             for w in wire["waves"] if w["final"]]
    assert waves == [(1, 8, 23, 34), (2, 34, 50, 57), (3, 77, 99, 108), (4, 108, 121, 130)]
    at = 130
    assert _value(episode, {"ref": "e", "field": "touch_number"})[at] == 4.0
    depth = _value(episode, {"ref": "e", "entity": "false_break", "index": -2, "field": "depth"})
    assert depth[at] == pytest.approx(2.19, abs=0.01)
    down = _value(episode, {"ref": "e", "entity": "down_leg", "index": 0, "field": "bars"})
    assert down[at] == 10.0


# -- section and operand validation ------------------------------------------------------


_STACK = {"anchor_stack": {"fast": {"period": 500}, "anchor": {"period": 1000},
                           "slow": {"period": 2000}}}


def test_section_defaults_come_from_the_anchor_stack() -> None:
    parsed = parse_episode_section({**_STACK, "ema_stack_episode": {"trend": {}}})
    assert parsed == {"trend": EpisodeParams(500, 1000, 2000, 24, 24, 15000)}
    custom = parse_episode_section(
        {**_STACK, "ema_stack_episode": {"t": {"window_bars": 12, "slow_period": 3000}}}
    )
    assert custom["t"] == EpisodeParams(500, 1000, 3000, 12, 12, 15000)
    assert parse_episode_section(_STACK) == {}


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": 1},
        {"window_bars": 0},
        {"break_bars": True},
        {"fast_period": 1000},
        {"history_bars": -1},
    ],
)
def test_invalid_section_is_rejected(params: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        parse_episode_section({**_STACK, "ema_stack_episode": {"trend": params}})


@pytest.mark.parametrize(
    "raw",
    [
        {"ref": "other", "field": "touch_number"},
        {"ref": "trend", "field": "range"},
        {"ref": "trend", "index": 0, "field": "touch_number"},
        {"ref": "trend", "entity": "zone", "field": "range"},
        {"ref": "trend", "entity": "zone", "index": "forming", "field": "range"},
        {"ref": "trend", "entity": "false_break", "index": "forming", "field": "depth"},
        {"ref": "trend", "entity": "leg", "index": 0, "field": "range"},
        {"ref": "trend", "entity": "zone", "index": 0, "field": "depth"},
        {"ref": "trend", "entity": "zone", "index": 1.5, "field": "range"},
    ],
)
def test_malformed_episode_reference_is_rejected(raw: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        parse_episode_ref(raw, "operand", frozenset({"trend"}))


def test_aliases_resolve_to_indices() -> None:
    refs = frozenset({"trend"})
    assert parse_episode_ref(
        {"ref": "trend", "entity": "wave", "index": "previous", "field": "peak_price"},
        "operand",
        refs,
    ) == EpisodeRef("trend", "wave", -1, "peak_price")
    assert parse_episode_ref(
        {"ref": "trend", "entity": "zone", "index": "current", "field": "bars"}, "operand", refs
    ).index == 0
