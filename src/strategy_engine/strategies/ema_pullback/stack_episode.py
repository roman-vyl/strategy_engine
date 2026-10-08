"""EMA stack episode: a causal projection of the current EMA-stack trend
(OpenSpec `ema-stack-episode-v1`).

The episode is a source of facts, not a context provider, a gate or an
exit consumption. Per side it records the episode boundaries, the touch
zones against the trend, their false breaks and the waves (origin `S*`,
peak `P`, up leg `S* -> P`, down leg `P -> touch`). It holds no metric.

It is rebuilt from the evaluated frame on every evaluation and never
stored between evaluations. Every value on bar `t` depends only on bars
`<= t`.

The short side runs the long state machine on mirrored prices (highs and
lows swapped and negated), so one rule set serves both sides.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.evaluation_context import EvaluationContext, compute_through
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.live_calculation.indicator_requirements import ema_warmup_bars

SECTION = "ema_stack_episode"
EPISODE_NODE_VERSION = 1

_SIDES = ("long", "short")
_PARAM_KEYS = frozenset(
    {"fast_period", "anchor_period", "slow_period", "window_bars", "break_bars", "history_bars"}
)
DEFAULT_WINDOW_BARS = 24
DEFAULT_HISTORY_BARS = 15000

STATE_FIELDS = (
    "active",
    "episode_id",
    "bars_since_start",
    "touch_number",
    "in_zone",
    "in_false_break",
    "away",
    "false_breaks",
    "censored",
)
EVENT_FIELDS = (
    "episode_start",
    "touch_start",
    "zone_end",
    "false_break_start",
    "comeback",
    "stack_break",
)
_RANGE_FIELDS = ("bars", "high", "low", "range", "start_bars_ago", "end_bars_ago", "final")
ENTITY_FIELDS: dict[str, frozenset[str]] = {
    "zone": frozenset({*_RANGE_FIELDS, "has_false_break"}),
    "false_break": frozenset({*_RANGE_FIELDS, "depth", "outcome_comeback"}),
    "up_leg": frozenset(_RANGE_FIELDS),
    "down_leg": frozenset(_RANGE_FIELDS),
    "wave": frozenset(
        {
            "origin_price",
            "peak_price",
            "touch_price",
            "bars",
            "start_bars_ago",
            "end_bars_ago",
            "final",
        }
    ),
}
FORMING_ENTITIES = frozenset({"wave", "up_leg", "down_leg"})


# -- parameters ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EpisodeParams:
    fast_period: int
    anchor_period: int
    slow_period: int
    window_bars: int
    break_bars: int
    history_bars: int

    def to_wire(self) -> dict[str, int]:
        return {
            "fast_period": self.fast_period,
            "anchor_period": self.anchor_period,
            "slow_period": self.slow_period,
            "window_bars": self.window_bars,
            "break_bars": self.break_bars,
            "history_bars": self.history_bars,
        }


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _positive_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError(f"{path} must be a positive integer")
    return value


def _stack_period(raw_spec: Mapping[str, Any], role: str) -> int:
    stack = _mapping(raw_spec.get("anchor_stack"), "anchor_stack")
    item = _mapping(stack.get(role), f"anchor_stack.{role}")
    return _positive_int(item.get("period"), f"anchor_stack.{role}.period")


def parse_episode_section(raw_spec: Mapping[str, Any]) -> dict[str, EpisodeParams]:
    """`episode_ref -> effective parameters`, in declared order. Empty when
    the spec declares no `ema_stack_episode` section."""

    raw = raw_spec.get(SECTION)
    if raw is None:
        return {}
    section = _mapping(raw, SECTION)
    out: dict[str, EpisodeParams] = {}
    for ref_raw, params_raw in section.items():
        ref = str(ref_raw)
        path = f"{SECTION}.{ref}"
        if not ref.strip():
            raise InvalidRequestError(f"{SECTION} episode_ref must be a non-empty string")
        params = _mapping(params_raw if params_raw is not None else {}, path)
        unknown = set(params) - _PARAM_KEYS
        if unknown:
            raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))
        periods = {
            role: (
                _positive_int(params[f"{role}_period"], f"{path}.{role}_period")
                if f"{role}_period" in params
                else _stack_period(raw_spec, role)
            )
            for role in ("fast", "anchor", "slow")
        }
        if not periods["fast"] < periods["anchor"] < periods["slow"]:
            raise InvalidRequestError(
                f"{path} periods must satisfy fast_period < anchor_period < slow_period",
                **{f"{role}_period": value for role, value in periods.items()},
            )
        window = (
            _positive_int(params["window_bars"], f"{path}.window_bars")
            if "window_bars" in params
            else DEFAULT_WINDOW_BARS
        )
        out[ref] = EpisodeParams(
            fast_period=periods["fast"],
            anchor_period=periods["anchor"],
            slow_period=periods["slow"],
            window_bars=window,
            break_bars=(
                _positive_int(params["break_bars"], f"{path}.break_bars")
                if "break_bars" in params
                else window
            ),
            history_bars=(
                _positive_int(params["history_bars"], f"{path}.history_bars")
                if "history_bars" in params
                else DEFAULT_HISTORY_BARS
            ),
        )
    return out


def episode_refs(raw_spec: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(parse_episode_section(raw_spec))


# -- projection ----------------------------------------------------------------

_AWAY, _ZONE, _FALSE_BREAK = 0, 1, 2


@dataclass(slots=True)
class SideEpisode:
    """One side's projection: per-bar state and snapshot series plus the
    entity tables. Prices are in the side's own (unmirrored) units.

    Per-bar snapshots hold the values of the latest zone, its false break
    and the forming wave as of each bar; the touch table holds every zone
    with its false break and its final wave (wave `k` is final at touch
    `k`, so zone and wave rows align). `first_row[e]` is the touch-table
    row of zone 1 of episode `e`."""

    side: str
    state: dict[str, np.ndarray]
    zone_now: dict[str, np.ndarray]
    false_break_now: dict[str, np.ndarray]
    forming: dict[str, np.ndarray]
    touches: dict[str, np.ndarray]
    first_row: np.ndarray
    episodes: list[dict[str, Any]] = field(default_factory=list)
    forming_rows: list[dict[str, Any]] = field(default_factory=list)


_STATE_KEYS = (*STATE_FIELDS, *EVENT_FIELDS)
_ZONE_NOW_KEYS = ("start", "end", "high", "low", "final", "has_false_break")
_FB_NOW_KEYS = ("start", "end", "high", "low", "depth", "outcome_comeback", "final")
_FORMING_KEYS = ("origin_bar", "origin_price", "peak_bar", "peak_price", "down_low", "down_high")
_TOUCH_KEYS = (
    "episode_id",
    "number",
    "zone_start",
    "zone_end",
    "zone_high",
    "zone_low",
    "zone_final",
    "zone_known_at",
    "has_false_break",
    "fb_start",
    "fb_end",
    "fb_high",
    "fb_low",
    "fb_depth",
    "fb_outcome_comeback",
    "fb_final",
    "fb_known_at",
    "origin_bar",
    "origin_price",
    "peak_bar",
    "peak_price",
    "touch_bar",
    "touch_price",
    "up_high",
    "up_low",
    "down_high",
    "down_low",
)


def _project_long(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fast: np.ndarray,
    anchor: np.ndarray,
    slow: np.ndarray,
    *,
    window: int,
    break_bars: int,
    censor_before: int,
) -> tuple[
    dict[str, list[float]],
    dict[str, list[float]],
    dict[str, list[float]],
    dict[str, list[float]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """The v6 state machine on long-side prices. One sequential pass."""

    nan = math.nan
    size = len(high)
    hi = high.tolist()
    lo = low.tolist()
    cl = close.tolist()
    fa = fast.tolist()
    an = anchor.tolist()
    sl = slow.tolist()

    state = {key: [nan] * size for key in _STATE_KEYS}
    state["active"] = [0.0] * size
    state["censored"] = [0.0] * size
    zone_now = {key: [nan] * size for key in _ZONE_NOW_KEYS}
    fb_now = {key: [nan] * size for key in _FB_NOW_KEYS}
    forming = {key: [nan] * size for key in _FORMING_KEYS}
    touches: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    forming_rows: list[dict[str, Any]] = []

    active = False
    censored = False
    episode_id = 0
    start = 0
    violation = 0
    touch_number = 0
    false_breaks = 0
    phase = _AWAY
    zone: dict[str, Any] | None = None
    # zone running values
    last_contact = 0
    all_low = all_high = 0.0
    run = 0
    run_low = run_high = 0.0
    fb_low = fb_high = 0.0
    # forming wave
    s_bar = p_bar = 0
    s_low = p_high = d_low = d_high = 0.0

    def reset_forming(i: int) -> None:
        nonlocal s_bar, p_bar, s_low, p_high, d_low, d_high
        s_bar = p_bar = i
        s_low = lo[i]
        p_high = d_high = hi[i]
        d_low = lo[i]

    def update_forming(i: int) -> None:
        nonlocal s_bar, p_bar, s_low, p_high, d_low, d_high
        if lo[i] < s_low:
            reset_forming(i)
            return
        if hi[i] > p_high:
            p_bar = i
            p_high = d_high = hi[i]
            d_low = lo[i]
            return
        if lo[i] < d_low:
            d_low = lo[i]

    def forming_row(final_at: int | None) -> dict[str, Any]:
        return {
            "episode_id": episode_id,
            "number": touch_number + 1,
            "origin_bar": s_bar,
            "origin_price": s_low,
            "peak_bar": p_bar,
            "peak_price": p_high,
            "up_high": p_high,
            "up_low": s_low,
            "down_high": d_high,
            "down_low": d_low,
            "end_bar": final_at,
        }

    for i in range(size):
        a = an[i]
        order = fa[i] > a > sl[i]  # False on any NaN
        if not active:
            if not order:
                continue
            active = True
            episode_id += 1
            start = i
            censored = i < censor_before
            violation = 0
            touch_number = 0
            false_breaks = 0
            phase = _AWAY
            zone = None
            reset_forming(i)
            episodes.append(
                {"episode_id": episode_id, "start_bar": i, "end_bar": None, "censored": censored}
            )
            events = {"episode_start": 1.0}
        else:
            events = {}
            violation = 0 if order else violation + 1
            if violation > break_bars:
                # Stack break: zone rules do not run; open entities become final.
                update_forming(i)
                if zone is not None and phase == _ZONE:
                    zone["zone_final"] = 1.0
                    zone["zone_known_at"] = i
                if zone is not None and phase == _FALSE_BREAK:
                    fb_low = min(fb_low, lo[i])
                    fb_high = max(fb_high, hi[i])
                    zone["fb_end"] = i
                    zone["fb_low"] = fb_low
                    zone["fb_high"] = fb_high
                    zone["fb_depth"] = zone["zone_low"] - fb_low
                    zone["fb_outcome_comeback"] = 0.0
                    zone["fb_final"] = 1.0
                    zone["fb_known_at"] = i
                phase = -1
                events = {"stack_break": 1.0}
                episodes[-1]["end_bar"] = i
                forming_rows.append({**forming_row(None), "stack_break_bar": i})
            elif not math.isfinite(a):
                update_forming(i)
            elif phase == _AWAY:
                if lo[i - 1] > an[i - 1] and lo[i] <= a <= hi[i]:
                    # Only above(t-1) -> contact(t) opens a zone: a gap from
                    # wholly above to wholly below is not a touch.
                    # Wave `touch_number + 1` is final here: its interval
                    # ends on the bar before the touch, its down leg on it.
                    wave = {
                        "origin_bar": s_bar,
                        "origin_price": s_low,
                        "peak_bar": p_bar,
                        "peak_price": p_high,
                        "touch_bar": i,
                        "touch_price": lo[i],
                        "up_high": p_high,
                        "up_low": s_low,
                        "down_high": max(d_high, hi[i]),
                        "down_low": min(d_low, lo[i]),
                    }
                    touch_number += 1
                    zone = {
                        "episode_id": episode_id,
                        "number": touch_number,
                        "zone_start": i,
                        "zone_end": i,
                        "zone_high": hi[i],
                        "zone_low": lo[i],
                        "zone_final": 0.0,
                        "zone_known_at": None,
                        "has_false_break": 0.0,
                        "fb_start": None,
                        "fb_end": None,
                        "fb_high": nan,
                        "fb_low": nan,
                        "fb_depth": nan,
                        "fb_outcome_comeback": nan,
                        "fb_final": nan,
                        "fb_known_at": None,
                        **wave,
                    }
                    touches.append(zone)
                    last_contact = i
                    all_low, all_high = lo[i], hi[i]
                    run = 0
                    run_low, run_high = lo[i], hi[i]
                    phase = _ZONE
                    events = {"touch_start": 1.0}
                    reset_forming(i)
                else:
                    update_forming(i)
            elif phase == _ZONE:
                assert zone is not None
                update_forming(i)
                all_low = min(all_low, lo[i])
                all_high = max(all_high, hi[i])
                if lo[i] > a:
                    run = 0
                    if i - last_contact > window:
                        zone["zone_final"] = 1.0
                        zone["zone_known_at"] = i
                        phase = _AWAY
                        events = {"zone_end": 1.0}
                elif hi[i] < a:
                    if run == 0:
                        run_low, run_high = lo[i], hi[i]
                    else:
                        run_low = min(run_low, lo[i])
                        run_high = max(run_high, hi[i])
                    run += 1
                    if run > window:
                        false_breaks += 1
                        zone["zone_final"] = 1.0
                        zone["zone_known_at"] = i
                        zone["has_false_break"] = 1.0
                        zone["fb_start"] = i - run + 1
                        zone["fb_end"] = i
                        fb_low, fb_high = run_low, run_high
                        zone["fb_low"] = fb_low
                        zone["fb_high"] = fb_high
                        zone["fb_depth"] = zone["zone_low"] - fb_low
                        zone["fb_final"] = 0.0
                        phase = _FALSE_BREAK
                        events = {"false_break_start": 1.0}
                else:
                    last_contact = i
                    run = 0
                    zone["zone_end"] = i
                    zone["zone_low"] = all_low
                    zone["zone_high"] = all_high
            else:  # _FALSE_BREAK
                assert zone is not None
                update_forming(i)
                fb_low = min(fb_low, lo[i])
                fb_high = max(fb_high, hi[i])
                zone["fb_end"] = i
                zone["fb_low"] = fb_low
                zone["fb_high"] = fb_high
                zone["fb_depth"] = zone["zone_low"] - fb_low
                if cl[i] > a:
                    zone["fb_outcome_comeback"] = 1.0
                    zone["fb_final"] = 1.0
                    zone["fb_known_at"] = i
                    phase = _AWAY
                    events = {"comeback": 1.0}

        state["active"][i] = 1.0
        state["censored"][i] = 1.0 if censored else 0.0
        if not censored:
            state["episode_id"][i] = float(episode_id)
            state["bars_since_start"][i] = float(i - start)
            state["touch_number"][i] = float(touch_number)
            state["in_zone"][i] = 1.0 if phase == _ZONE else 0.0
            state["in_false_break"][i] = 1.0 if phase == _FALSE_BREAK else 0.0
            state["away"][i] = 1.0 if phase == _AWAY else 0.0
            state["false_breaks"][i] = float(false_breaks)
            for key in EVENT_FIELDS:
                state[key][i] = events.get(key, 0.0)
            if zone is not None:
                zone_now["start"][i] = zone["zone_start"]
                zone_now["end"][i] = zone["zone_end"]
                zone_now["high"][i] = zone["zone_high"]
                zone_now["low"][i] = zone["zone_low"]
                zone_now["final"][i] = zone["zone_final"]
                zone_now["has_false_break"][i] = zone["has_false_break"]
                if zone["fb_start"] is not None:
                    fb_now["start"][i] = zone["fb_start"]
                    fb_now["end"][i] = zone["fb_end"]
                    fb_now["high"][i] = zone["fb_high"]
                    fb_now["low"][i] = zone["fb_low"]
                    fb_now["depth"][i] = zone["fb_depth"]
                    fb_now["outcome_comeback"][i] = zone["fb_outcome_comeback"]
                    fb_now["final"][i] = zone["fb_final"]
            forming["origin_bar"][i] = s_bar
            forming["origin_price"][i] = s_low
            forming["peak_bar"][i] = p_bar
            forming["peak_price"][i] = p_high
            forming["down_low"][i] = d_low
            forming["down_high"][i] = d_high
        if phase == -1:
            active = False
            zone = None

    if active:
        forming_rows.append({**forming_row(None), "stack_break_bar": None})
    return state, zone_now, fb_now, forming, touches, episodes, forming_rows


def _to_array(values: list[float]) -> np.ndarray:
    array = np.array(values, dtype=np.float64)
    array.flags.writeable = False
    return array


def _bar(value: object) -> float:
    return math.nan if value is None else float(value)  # type: ignore[arg-type]


# Mirrored price fields: (output key, mirrored key it is read from).
_SWAPS = (
    ("zone_high", "zone_low"),
    ("fb_high", "fb_low"),
    ("up_high", "up_low"),
    ("down_high", "down_low"),
)
_PRICE_KEYS = ("origin_price", "peak_price", "touch_price")


def _unmirror_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for high_key, low_key in _SWAPS:
        if high_key in row:
            out[high_key] = -row[low_key]
            out[low_key] = -row[high_key]
    for key in _PRICE_KEYS:
        if key in row:
            out[key] = -row[key]
    return out


def project_side(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fast: np.ndarray,
    anchor: np.ndarray,
    slow: np.ndarray,
    params: EpisodeParams,
    side: str,
) -> SideEpisode:
    """The causal projection of one side. Censoring counts the slow EMA's
    warm-up, by the existing per-feature live policy, from the first bar of
    the evaluated arrays."""

    if side not in _SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    short = side == "short"
    state, zone_now, fb_now, forming, touches, episodes, forming_rows = _project_long(
        -low if short else high,
        -high if short else low,
        -close if short else close,
        -fast if short else fast,
        -anchor if short else anchor,
        -slow if short else slow,
        window=params.window_bars,
        break_bars=params.break_bars,
        censor_before=ema_warmup_bars(params.slow_period),
    )
    if short:
        zone_now["high"], zone_now["low"] = (
            [-v for v in zone_now["low"]],
            [-v for v in zone_now["high"]],
        )
        fb_now["high"], fb_now["low"] = (
            [-v for v in fb_now["low"]],
            [-v for v in fb_now["high"]],
        )
        forming["origin_price"] = [-v for v in forming["origin_price"]]
        forming["peak_price"] = [-v for v in forming["peak_price"]]
        forming["down_high"], forming["down_low"] = (
            [-v for v in forming["down_low"]],
            [-v for v in forming["down_high"]],
        )
        touches = [_unmirror_row(row) for row in touches]
        forming_rows = [_unmirror_row(row) for row in forming_rows]

    first_row = np.full(len(episodes) + 1, -1, dtype=np.int64)
    for row_index, row in enumerate(touches):
        if first_row[row["episode_id"]] < 0:
            first_row[row["episode_id"]] = row_index
    first_row.flags.writeable = False
    return SideEpisode(
        side=side,
        state={key: _to_array(values) for key, values in state.items()},
        zone_now={key: _to_array(values) for key, values in zone_now.items()},
        false_break_now={key: _to_array(values) for key, values in fb_now.items()},
        forming={key: _to_array(values) for key, values in forming.items()},
        touches={
            key: _to_array([_bar(row[key]) for row in touches]) for key in _TOUCH_KEYS
        },
        first_row=first_row,
        episodes=episodes,
        forming_rows=forming_rows,
    )


# -- bundle ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EpisodeOutput:
    episode_ref: str
    params: EpisodeParams
    sides: dict[str, SideEpisode]


@dataclass(frozen=True, slots=True)
class EpisodeBundle:
    """Every declared episode evaluated once for one feature frame. It lives
    beside the `ContextBundle` and is never a context provider."""

    time_ms: tuple[int, ...]
    outputs: tuple[EpisodeOutput, ...]

    def side(self, episode_ref: str, side: str) -> SideEpisode:
        for output in self.outputs:
            if output.episode_ref == episode_ref:
                return output.sides[side]
        raise InvalidRequestError("episode is not evaluated", episode_ref=episode_ref)

    def to_wire(self) -> dict[str, object]:
        return {
            "time_ms": list(self.time_ms),
            "items": {
                output.episode_ref: {
                    "params": output.params.to_wire(),
                    "sides": {
                        side: side_to_wire(episode, self.time_ms)
                        for side, episode in output.sides.items()
                    },
                }
                for output in self.outputs
            },
        }


def _float_or_none(value: float) -> float | None:
    return None if not math.isfinite(value) else float(value)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    number = float(value)  # type: ignore[arg-type]
    return None if not math.isfinite(number) else int(number)


def side_to_wire(episode: SideEpisode, time_ms: tuple[int, ...]) -> dict[str, object]:
    """State series on the frame's time axis and the entity tables of every
    non-censored episode. Bars are given as index and as `time_ms`."""

    def at(bar: object) -> dict[str, int | None]:
        index = _int_or_none(bar)
        return {"bar": index, "time_ms": None if index is None else time_ms[index]}

    censored = {row["episode_id"] for row in episode.episodes if row["censored"]}
    touches = episode.touches
    zones: list[dict[str, object]] = []
    false_breaks: list[dict[str, object]] = []
    waves: list[dict[str, object]] = []
    for row in range(len(touches["number"])):
        episode_id = int(touches["episode_id"][row])
        if episode_id in censored:
            continue
        number = int(touches["number"][row])
        zone_final = touches["zone_final"][row] == 1.0
        zones.append(
            {
                "episode_id": episode_id,
                "number": number,
                "start": at(touches["zone_start"][row]),
                "end": at(touches["zone_end"][row]),
                "high": float(touches["zone_high"][row]),
                "low": float(touches["zone_low"][row]),
                "has_false_break": bool(touches["has_false_break"][row] == 1.0),
                "final": bool(zone_final),
                "known_at": at(touches["zone_known_at"][row]),
            }
        )
        if touches["has_false_break"][row] == 1.0:
            outcome = touches["fb_outcome_comeback"][row]
            false_breaks.append(
                {
                    "episode_id": episode_id,
                    "number": number,
                    "start": at(touches["fb_start"][row]),
                    "end": at(touches["fb_end"][row]),
                    "high": float(touches["fb_high"][row]),
                    "low": float(touches["fb_low"][row]),
                    "depth": float(touches["fb_depth"][row]),
                    "outcome": (
                        None
                        if not math.isfinite(outcome)
                        else "comeback" if outcome == 1.0 else "stack_break"
                    ),
                    "final": bool(touches["fb_final"][row] == 1.0),
                    "known_at": at(touches["fb_known_at"][row]),
                }
            )
        waves.append(
            {
                "episode_id": episode_id,
                "number": number,
                "origin": at(touches["origin_bar"][row]),
                "origin_price": float(touches["origin_price"][row]),
                "peak": at(touches["peak_bar"][row]),
                "peak_price": float(touches["peak_price"][row]),
                "touch": at(touches["touch_bar"][row]),
                "touch_price": float(touches["touch_price"][row]),
                "up_leg": {
                    "high": float(touches["up_high"][row]),
                    "low": float(touches["up_low"][row]),
                },
                "down_leg": {
                    "high": float(touches["down_high"][row]),
                    "low": float(touches["down_low"][row]),
                },
                "final": True,
                "known_at": at(touches["touch_bar"][row]),
            }
        )
    for forming in episode.forming_rows:
        if forming["episode_id"] in censored:
            continue
        waves.append(
            {
                "episode_id": forming["episode_id"],
                "number": forming["number"],
                "origin": at(forming["origin_bar"]),
                "origin_price": forming["origin_price"],
                "peak": at(forming["peak_bar"]),
                "peak_price": forming["peak_price"],
                "touch": at(None),
                "touch_price": None,
                "up_leg": {"high": forming["up_high"], "low": forming["up_low"]},
                "down_leg": {"high": forming["down_high"], "low": forming["down_low"]},
                "final": False,
                "known_at": at(None),
                "stack_break": at(forming["stack_break_bar"]),
            }
        )
    return {
        "state": {
            key: [_float_or_none(value) for value in episode.state[key].tolist()]
            for key in (*STATE_FIELDS, *EVENT_FIELDS)
        },
        "episodes": [
            {
                "episode_id": row["episode_id"],
                "start": at(row["start_bar"]),
                "stack_break": at(row["end_bar"]),
                "censored": row["censored"],
            }
            for row in episode.episodes
        ],
        "zones": zones,
        "false_breaks": false_breaks,
        "waves": waves,
    }


def _series(frame: FeatureFrameLike, output_id: str) -> np.ndarray:
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc
    array = np.fromiter(
        (math.nan if value is None else float(value) for value in values),
        dtype=np.float64,
        count=len(values),
    )
    array[~np.isfinite(array)] = math.nan
    return array


def _compute_side(
    frame: FeatureFrameLike, columns: Mapping[str, str], params: EpisodeParams, side: str
) -> SideEpisode:
    market = frame_market_arrays(frame)
    return project_side(
        market.array("high"),
        market.array("low"),
        market.array("close"),
        _series(frame, columns["fast"]),
        _series(frame, columns["anchor"]),
        _series(frame, columns["slow"]),
        params,
        side,
    )


def build_episode_bundle(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    episode_columns: Mapping[str, Mapping[str, str]],
    *,
    context: EvaluationContext | None = None,
    identities: Mapping[str, NodeSpec] | None = None,
) -> EpisodeBundle | None:
    """Every declared episode, once per side, or `None` when the spec
    declares none. `identities`: `episode_identity_key -> node` for memoized
    evaluation."""

    declared = parse_episode_section(raw_spec)
    if not declared:
        return None
    outputs: list[EpisodeOutput] = []
    for ref, params in declared.items():
        columns = episode_columns.get(ref)
        if columns is None:
            raise InvalidRequestError("episode has no feature-plan mapping", episode_ref=ref)
        sides = {
            side: compute_through(
                context,
                identities.get(episode_identity_key(ref, side)) if identities else None,
                functools.partial(_compute_side, frame, columns, params, side),
            )
            for side in _SIDES
        }
        outputs.append(EpisodeOutput(ref, params, sides))
    return EpisodeBundle(time_ms=frame.time_ms, outputs=tuple(outputs))


# -- identity ----------------------------------------------------------------------


def episode_identity_key(episode_ref: str, side: str) -> str:
    """Key of an episode node inside the strategy's context identity map.
    The NUL prefix keeps it apart from every declared `context_ref`."""

    return f"\x00{SECTION}:{side}:{episode_ref}"


def resolve_episode_identities(
    raw_spec: Mapping[str, Any],
    episode_columns: Mapping[str, Mapping[str, str]],
    feature_ids: Mapping[str, NodeSpec],
) -> dict[str, NodeSpec]:
    """`episode_identity_key -> node` of every declared episode and side.
    The `episode_ref` label is not part of any identity."""

    out: dict[str, NodeSpec] = {}
    for ref, params in parse_episode_section(raw_spec).items():
        columns = episode_columns.get(ref)
        if columns is None:
            raise InvalidRequestError("episode has no feature-plan mapping", episode_ref=ref)
        upstream = {role: feature_ids.get(columns[role]) for role in ("fast", "anchor", "slow")}
        for side in _SIDES:
            out[episode_identity_key(ref, side)] = node_spec(
                "episode.ema_stack",
                version=EPISODE_NODE_VERSION,
                params={
                    "window_bars": params.window_bars,
                    "break_bars": params.break_bars,
                    "history_bars": params.history_bars,
                },
                upstream=upstream,
                side=side,
            )
    return out


# -- operand -----------------------------------------------------------------------

_INDEX_ALIASES: dict[str, int | str] = {"current": 0, "previous": -1, "forming": "forming"}


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    """`{"episode": {"ref", "entity", "index", "field"}}`: a state field
    when `entity` is None, otherwise one field of one entity. `index` is an
    int (`<= 0` counted back from the latest touch, `> 0` the number in the
    episode) or `"forming"`."""

    ref: str
    entity: str | None
    index: int | str | None
    field: str

    def identity_params(self) -> tuple[object, ...]:
        return (self.entity, self.index, self.field)


def parse_episode_ref(raw: object, path: str, refs: frozenset[str] | None) -> EpisodeRef:
    payload = _mapping(raw, path)
    unknown = set(payload) - {"ref", "entity", "index", "field"}
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))
    ref = payload.get("ref")
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.ref must be a non-empty string")
    if refs is not None and ref not in refs:
        raise InvalidRequestError(f"{path}.ref is not declared in {SECTION}", ref=ref)
    field_name = payload.get("field")
    if not isinstance(field_name, str) or not field_name:
        raise InvalidRequestError(f"{path}.field must be a non-empty string")
    entity = payload.get("entity")
    has_index = "index" in payload
    if entity is None:
        if has_index:
            raise InvalidRequestError(f"{path}.index requires entity")
        if field_name not in (*STATE_FIELDS, *EVENT_FIELDS):
            raise InvalidRequestError(
                f"{path}.field is not an episode state field", field=field_name
            )
        return EpisodeRef(ref, None, None, field_name)
    if entity not in ENTITY_FIELDS:
        raise InvalidRequestError(
            f"{path}.entity must be one of {', '.join(ENTITY_FIELDS)}", entity=entity
        )
    if not has_index:
        raise InvalidRequestError(f"{path}.entity requires index")
    raw_index = payload.get("index")
    index: int | str
    if isinstance(raw_index, str) and raw_index in _INDEX_ALIASES:
        index = _INDEX_ALIASES[raw_index]
    elif isinstance(raw_index, int) and not isinstance(raw_index, bool):
        index = raw_index
    else:
        raise InvalidRequestError(
            f"{path}.index must be an integer, current, previous or forming", index=raw_index
        )
    if index == "forming" and entity not in FORMING_ENTITIES:
        raise InvalidRequestError(f"{path}.index forming is allowed for wave, up_leg, down_leg")
    if field_name not in ENTITY_FIELDS[entity]:
        raise InvalidRequestError(
            f"{path}.field is not a field of {entity}", field=field_name
        )
    return EpisodeRef(ref, str(entity), index, field_name)


def _range_field(
    name: str,
    t: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    final: np.ndarray,
) -> np.ndarray:
    if name == "bars":
        return np.asarray(end - start + 1, dtype=np.float64)
    if name == "high":
        return high
    if name == "low":
        return low
    if name == "range":
        return np.asarray(high - low, dtype=np.float64)
    if name == "start_bars_ago":
        return np.asarray(t - start, dtype=np.float64)
    if name == "end_bars_ago":
        return np.asarray(t - end, dtype=np.float64)
    assert name == "final"
    return final


def _take(column: np.ndarray, rows: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(len(rows), math.nan)
    out[mask] = column[rows[mask]]
    return out


def episode_operand_values(episode: SideEpisode, operand: EpisodeRef) -> np.ndarray:
    """The operand on every bar as a read-only float64 array; missing
    values (no active episode, censored, an entity not reached, an index out
    of range) are NaN. O(bars) gathers."""

    state = episode.state
    if operand.entity is None:
        values = np.array(state[operand.field], dtype=np.float64)
        values.flags.writeable = False
        return values

    size = len(state["active"])
    t = np.arange(size, dtype=np.float64)
    nan = np.full(size, math.nan)
    touch_number = state["touch_number"]  # NaN when inactive or censored
    live = np.isfinite(touch_number)
    entity = operand.entity
    name = operand.field

    with np.errstate(invalid="ignore"):
        if operand.index == "forming":
            forming = episode.forming
            if entity == "wave":
                start, end = forming["origin_bar"], t
                values = {
                    "origin_price": forming["origin_price"],
                    "peak_price": forming["peak_price"],
                    "touch_price": nan,
                    "bars": end - start + 1,
                    "start_bars_ago": t - start,
                    "end_bars_ago": t - end,
                    "final": np.zeros(size),
                }[name]
            elif entity == "up_leg":
                values = _range_field(
                    name,
                    t,
                    forming["origin_bar"],
                    forming["peak_bar"],
                    forming["peak_price"],
                    forming["origin_price"],
                    np.zeros(size),
                )
            else:
                values = _range_field(
                    name,
                    t,
                    forming["peak_bar"],
                    t,
                    forming["down_high"],
                    forming["down_low"],
                    np.zeros(size),
                )
            out = np.where(live, values, math.nan)
        else:
            assert isinstance(operand.index, int)
            m = np.where(live, touch_number, 0.0)
            number = m + operand.index if operand.index <= 0 else np.full(size, operand.index)
            valid = live & (number >= 1) & (number <= m)
            episode_id = np.where(live, state["episode_id"], 0.0).astype(np.int64)
            first = episode.first_row[np.clip(episode_id, 0, len(episode.first_row) - 1)]
            rows = np.where(valid, first + number.astype(np.int64) - 1, 0)
            touches = episode.touches

            def table(key: str) -> np.ndarray:
                return _take(touches[key], rows, valid)

            if entity in ("zone", "false_break"):
                current = valid & (number == m)
                now = episode.zone_now if entity == "zone" else episode.false_break_now
                prefix = "zone" if entity == "zone" else "fb"
                keys = {
                    "start": f"{prefix}_start",
                    "end": f"{prefix}_end",
                    "high": f"{prefix}_high",
                    "low": f"{prefix}_low",
                    "final": f"{prefix}_final",
                }
                if entity == "zone":
                    keys["has_false_break"] = "has_false_break"
                else:
                    keys["depth"] = "fb_depth"
                    keys["outcome_comeback"] = "fb_outcome_comeback"

                def pick(key: str) -> np.ndarray:
                    return np.where(current, now[key], table(keys[key]))

                if name in ("has_false_break", "depth", "outcome_comeback"):
                    values = pick(name)
                else:
                    values = _range_field(
                        name, t, pick("start"), pick("end"), pick("high"), pick("low"),
                        pick("final"),
                    )
            elif entity == "wave":
                start, end = table("origin_bar"), table("touch_bar")
                values = {
                    "origin_price": table("origin_price"),
                    "peak_price": table("peak_price"),
                    "touch_price": table("touch_price"),
                    "bars": end - start + 1,
                    "start_bars_ago": t - start,
                    "end_bars_ago": t - end,
                    "final": np.ones(size),
                }[name]
            elif entity == "up_leg":
                values = _range_field(
                    name,
                    t,
                    table("origin_bar"),
                    table("peak_bar"),
                    table("up_high"),
                    table("up_low"),
                    np.ones(size),
                )
            else:
                values = _range_field(
                    name,
                    t,
                    table("peak_bar"),
                    table("touch_bar"),
                    table("down_high"),
                    table("down_low"),
                    np.ones(size),
                )
            out = np.where(valid, values, math.nan)
    out = np.asarray(out, dtype=np.float64)
    out[~np.isfinite(out)] = math.nan
    out.flags.writeable = False
    return out
