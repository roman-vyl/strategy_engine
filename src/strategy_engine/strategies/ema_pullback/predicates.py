"""Pre-entry predicates: the internal boolean layer between canonical
features and `composite_setup` (OpenSpec
`composite-setup-pre-entry-predicates-v1`, design D2-D5, D7, D8, D10).

A predicate is not a strategy role. It reads only canonical plan columns
(through one memoized float64 array per feature identity) and the frame's
shared market arrays, and returns a bool array on the base timeline.

This module knows no indicator kinds, sources or parameters: a feature
operand is an opaque request resolved only through the canonical
feature-kind contract (`plan_feature_request`, design D13).
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.indicators.contracts import FeatureFrameLike, PlannedFeature
from strategy_engine.indicators.evaluation_context import EvaluationContext, compute_through
from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.ema_pullback.stack_episode import (
    EpisodeRef,
    SideEpisode,
    episode_identity_key,
    episode_operand_values,
    parse_episode_ref,
)

if TYPE_CHECKING:
    from strategy_engine.strategies.ema_pullback.contexts import ContextBundle

PREDICATE_NODE_VERSION = 1

_PRICE_FIELDS = frozenset({"open", "high", "low", "close"})
_COMPARE_OPS: dict[str, Callable[[Any, Any], np.ndarray]] = {
    ">": np.greater,
    ">=": np.greater_equal,
    "<": np.less,
    "<=": np.less_equal,
}
_SIDES = frozenset({"long", "short"})


@dataclass(frozen=True, slots=True)
class SegmentSeries:
    """The series a segment aggregates: one feature, or `left - right` of
    two features (OpenSpec `a1-band-filter-v1`, design D2)."""

    left: PlannedFeature
    right: PlannedFeature | None = None
    by_side: bool = False

    def features(self) -> tuple[PlannedFeature, ...]:
        return (self.left,) if self.right is None else (self.left, self.right)

    def for_side(self, side: str) -> PlannedFeature:
        """The feature a `by_side` series reads on `side` (`left` is the long
        side, `right` the short side; `b2-di-wave-v1`, design D2)."""

        assert self.by_side and self.right is not None
        return self.left if side == "long" else self.right


@dataclass(frozen=True, slots=True)
class Eligibility:
    """Conditions on both legs of the current touch under which a segment has
    a value (`a2-shape-aggregates-v1`, design D5)."""

    legs_min_bars: int | None = None
    window: int | None = None
    impulse_positive: bool = False
    pullback_min_bars: int | None = None


@dataclass(frozen=True, slots=True)
class Segment:
    """An aggregate of a series over a leg of the current touch of an EMA
    stack episode (`a1-band-filter-v1`, design D2; `span`, `top` and
    `eligibility` from `a2-shape-aggregates-v1`)."""

    episode: str
    series: SegmentSeries
    start: str
    end: str
    aggregate: str
    value: str = "level"
    last_n: int | None = None
    negate: bool = False
    span: int | None = None
    top: int | None = None
    eligibility: Eligibility | None = None
    touch: str = "current"


@dataclass(frozen=True, slots=True)
class Ratio:
    left: Operand
    right: Operand
    right_floor: float = 0.0


@dataclass(frozen=True, slots=True)
class Operand:
    """Exactly one of a canonical feature request, an EMA stack episode
    reference, a segment aggregate, a ratio, a base-bar price field or a
    numeric constant."""

    feature: PlannedFeature | None = None
    price: str | None = None
    const: float | None = None
    episode: EpisodeRef | None = None
    segment: Segment | None = None
    ratio: Ratio | None = None


@dataclass(frozen=True, slots=True)
class Compare:
    left: Operand
    op: str
    right: Operand


@dataclass(frozen=True, slots=True)
class Range:
    """`min` / `max` of None are "no control" on that side; `bounds` picks
    inclusive or exclusive comparison, `empty` the result on a non-finite
    operand (OpenSpec `a1-band-filter-v1`, design D4)."""

    operand: Operand
    min: float | None
    max: float | None
    bounds: str = "inclusive"
    empty: str = "block"


@dataclass(frozen=True, slots=True)
class Change:
    """`operand(j) - operand(j - lookback) <op> value` where `j` is the last
    completed bar of the operand's own timeframe and `lookback` counts bars of
    that timeframe (OpenSpec `predicate-change-class-v1`, design D2)."""

    operand: Operand
    lookback: int
    op: str
    value: float


Condition = Compare | Range | Change


@dataclass(frozen=True, slots=True)
class Predicate:
    """One parsed predicate: its long condition and, only with an explicit
    `short` override (design D3), a different short condition."""

    long: Condition
    short: Condition | None

    def for_side(self, side: str) -> Condition:
        if side == "short" and self.short is not None:
            return self.short
        return self.long

    def features(self) -> tuple[PlannedFeature, ...]:
        """Every feature request of every side, in declared order."""

        out: list[PlannedFeature] = []
        for condition in (self.long, self.short):
            for operand in _operands(condition):
                out.extend(operand_features(operand))
        return tuple(out)


@dataclass(frozen=True, slots=True)
class StatePredicate:
    """HTF regime of a declared context, side-relative through the existing
    regime resolution (design D3, D9). Reads the context bundle only."""

    context_ref: str
    regimes: tuple[str, ...]  # sorted, unique subset of aligned/countertrend/neutral

    def features(self) -> tuple[PlannedFeature, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class TemporalPredicate:
    """`held_for` / `within` over a non-temporal predicate, in base bars
    (design D4)."""

    mode: str
    bars: int
    of: Predicate | StatePredicate

    def features(self) -> tuple[PlannedFeature, ...]:
        return self.of.features()


AnyPredicate = Predicate | StatePredicate | TemporalPredicate


def operand_features(operand: Operand) -> tuple[PlannedFeature, ...]:
    """Every feature request an operand reads, in evaluation order."""

    if operand.feature is not None:
        return (operand.feature,)
    if operand.segment is not None:
        return operand.segment.series.features()
    if operand.ratio is not None:
        return (*operand_features(operand.ratio.left), *operand_features(operand.ratio.right))
    return ()


def operand_needs_episode(operand: Operand) -> bool:
    """True iff the operand reads the EMA stack episode bundle."""

    if operand.episode is not None or operand.segment is not None:
        return True
    return operand.ratio is not None and (
        operand_needs_episode(operand.ratio.left) or operand_needs_episode(operand.ratio.right)
    )


def _operands(condition: Condition | None) -> tuple[Operand, ...]:
    if condition is None:
        return ()
    if isinstance(condition, Compare):
        return (condition.left, condition.right)
    return (condition.operand,)


# -- parsing (market-data-free, design D12) ------------------------------------


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _only_fields(payload: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRequestError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise InvalidRequestError(f"{path} must be finite")
    return result


def _feature(raw: object, path: str) -> PlannedFeature:
    payload = _mapping(raw, path)
    _only_fields(payload, {"kind", "timeframe", "source", "params"}, path)
    kind = payload.get("kind")
    if not isinstance(kind, str) or not kind:
        raise InvalidRequestError(f"{path}.kind must be a non-empty string")
    timeframe = payload.get("timeframe")
    if timeframe is not None:
        if not isinstance(timeframe, str) or not timeframe:
            raise InvalidRequestError(f"{path}.timeframe must be a non-empty string")
        if timeframe != "base":
            timeframe_duration_ms(timeframe)
    source = payload.get("source")
    if source is not None and not isinstance(source, str):
        raise InvalidRequestError(f"{path}.source must be a string")
    params = _mapping(payload.get("params", {}), f"{path}.params")
    return plan_feature_request(kind, timeframe, source, params)


_OPERAND_KEYS = "feature, episode, segment, ratio, price or const"
_SEGMENT_FIELDS = {
    "episode",
    "of",
    "from",
    "to",
    "aggregate",
    "value",
    "window",
    "negate",
    "span",
    "top",
    "eligibility",
    "touch",
}
_SEGMENT_REQUIRED = ("episode", "of", "from", "to", "aggregate")
_SEGMENT_SPANS = frozenset({("origin", "peak"), ("peak", "current"), ("origin", "current")})
_SEGMENT_AGGREGATES = frozenset(
    {"sum", "mean_per_bar", "max", "min", "abs_sum", "top_abs_sum", "top_abs_share"}
)
_SEGMENT_VALUES = frozenset({"level", "change", "change_over", "from_start"})
_SEGMENT_TOUCHES = frozenset({"current", "previous"})
_SEGMENT_CHANGE_AGGREGATES = frozenset({"max", "min", "abs_sum", "top_abs_sum", "top_abs_share"})
_ELIGIBILITY_FIELDS = {"legs_min_bars", "window", "impulse_positive", "pullback_min_bars"}


def _positive_int(raw: object, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise InvalidRequestError(f"{path} must be a positive integer", value=raw)
    return raw


def _eligibility(raw: object, path: str) -> Eligibility:
    payload = _mapping(raw, path)
    _only_fields(payload, _ELIGIBILITY_FIELDS, path)
    legs = payload.get("legs_min_bars")
    pullback_min = payload.get("pullback_min_bars")
    window = payload.get("window")
    positive = payload.get("impulse_positive", False)
    if not isinstance(positive, bool):
        raise InvalidRequestError(f"{path}.impulse_positive must be a boolean")
    if positive and window is None:
        raise InvalidRequestError(f"{path}.impulse_positive requires window")
    return Eligibility(
        None if legs is None else _positive_int(legs, f"{path}.legs_min_bars"),
        None if window is None else _positive_int(window, f"{path}.window"),
        positive,
        None if pullback_min is None else _positive_int(pullback_min, f"{path}.pullback_min_bars"),
    )


def _segment_series(raw: object, path: str) -> SegmentSeries:
    payload = _mapping(raw, path)
    if "by_side" in payload:
        if len(payload) != 1:
            raise InvalidRequestError(f"{path} must carry only by_side")
        sides = _mapping(payload["by_side"], f"{path}.by_side")
        _only_fields(sides, {"long", "short"}, f"{path}.by_side")
        if set(sides) != {"long", "short"}:
            raise InvalidRequestError(f"{path}.by_side needs exactly long and short")
        return SegmentSeries(
            _feature(sides["long"], f"{path}.by_side.long"),
            _feature(sides["short"], f"{path}.by_side.short"),
            by_side=True,
        )
    if "difference" not in payload:
        return SegmentSeries(_feature(payload, path))
    if len(payload) != 1:
        raise InvalidRequestError(f"{path} must carry only difference")
    difference = _mapping(payload["difference"], f"{path}.difference")
    _only_fields(difference, {"left", "right"}, f"{path}.difference")
    return SegmentSeries(
        _feature(difference.get("left"), f"{path}.difference.left"),
        _feature(difference.get("right"), f"{path}.difference.right"),
    )


def _segment(raw: object, path: str, episode_refs: frozenset[str] | None) -> Segment:
    payload = _mapping(raw, path)
    _only_fields(payload, _SEGMENT_FIELDS, path)
    for key in _SEGMENT_REQUIRED:
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    start, end = payload["from"], payload["to"]
    if (start, end) not in _SEGMENT_SPANS:
        raise InvalidRequestError(
            f"{path}.from/to must be origin-peak, peak-current or origin-current",
            start=start,
            end=end,
        )
    aggregate = payload["aggregate"]
    if aggregate not in _SEGMENT_AGGREGATES:
        raise InvalidRequestError(
            f"{path}.aggregate must be one of {sorted(_SEGMENT_AGGREGATES)}",
            aggregate=aggregate,
        )
    value = payload.get("value", "level")
    if value not in _SEGMENT_VALUES:
        raise InvalidRequestError(
            f"{path}.value must be level, change, change_over or from_start", value=value
        )
    if value == "from_start" and aggregate not in ("sum", "mean_per_bar", "max", "min"):
        raise InvalidRequestError(f"{path}.{aggregate} is not defined for from_start")
    if value == "from_start" and "window" in payload:
        raise InvalidRequestError(f"{path}.window is not allowed with from_start")
    touch = payload.get("touch", "current")
    if touch not in _SEGMENT_TOUCHES:
        raise InvalidRequestError(f"{path}.touch must be current or previous", touch=touch)
    if touch == "previous" and (start, end) != ("origin", "peak"):
        raise InvalidRequestError(f"{path}.touch previous needs from origin to peak")
    span: int | None = None
    if value == "change_over":
        if "span" not in payload:
            raise InvalidRequestError(f"{path}.span is required with change_over")
        span = _positive_int(payload["span"], f"{path}.span")
    elif "span" in payload:
        raise InvalidRequestError(f"{path}.span is only allowed with change_over")
    if aggregate in _SEGMENT_CHANGE_AGGREGATES and value == "level":
        raise InvalidRequestError(f"{path}.{aggregate} needs value change or change_over")
    if value == "change_over" and aggregate in ("sum", "mean_per_bar"):
        raise InvalidRequestError(f"{path}.{aggregate} is not defined for change_over")
    top: int | None = None
    if aggregate in ("top_abs_sum", "top_abs_share"):
        if "top" not in payload:
            raise InvalidRequestError(f"{path}.top is required with {aggregate}")
        top = _positive_int(payload["top"], f"{path}.top")
        window_payload = payload.get("window")
        if window_payload is None:
            raise InvalidRequestError(f"{path}.window.last_n is required with {aggregate}")
    elif "top" in payload:
        raise InvalidRequestError(f"{path}.top is only allowed with top_abs_sum or top_abs_share")
    last_n: int | None = None
    window = payload.get("window")
    if window is not None:
        window = _mapping(window, f"{path}.window")
        _only_fields(window, {"last_n"}, f"{path}.window")
        last_n = window.get("last_n")
        if isinstance(last_n, bool) or not isinstance(last_n, int) or last_n < 1:
            raise InvalidRequestError(
                f"{path}.window.last_n must be a positive integer", last_n=last_n
            )
    negate = payload.get("negate", False)
    if not isinstance(negate, bool):
        raise InvalidRequestError(f"{path}.negate must be a boolean")
    eligibility = payload.get("eligibility")
    return Segment(
        ref,
        _segment_series(payload["of"], f"{path}.of"),
        str(start),
        str(end),
        str(aggregate),
        str(value),
        last_n,
        negate,
        span,
        top,
        None if eligibility is None else _eligibility(eligibility, f"{path}.eligibility"),
        str(touch),
    )


def _ratio(raw: object, path: str, episode_refs: frozenset[str] | None) -> Ratio:
    payload = _mapping(raw, path)
    _only_fields(payload, {"left", "right", "right_floor"}, path)
    floor = 0.0
    if "right_floor" in payload:
        floor = _number(payload["right_floor"], f"{path}.right_floor")
    left = _operand(payload.get("left"), f"{path}.left", episode_refs)
    right = _operand(payload.get("right"), f"{path}.right", episode_refs)
    if left.ratio is not None or right.ratio is not None:
        raise InvalidRequestError(f"{path} must not nest a ratio")
    if left.const is not None and right.const is not None:
        raise InvalidRequestError(f"{path} must have at least one non-constant side")
    return Ratio(left, right, floor)


def _operand(raw: object, path: str, episode_refs: frozenset[str] | None) -> Operand:
    payload = _mapping(raw, path)
    if len(payload) != 1:
        raise InvalidRequestError(f"{path} must carry exactly one of {_OPERAND_KEYS}")
    ((key, value),) = payload.items()
    if key == "feature":
        return Operand(feature=_feature(value, f"{path}.feature"))
    if key == "episode":
        return Operand(episode=parse_episode_ref(value, f"{path}.episode", episode_refs))
    if key == "segment":
        return Operand(segment=_segment(value, f"{path}.segment", episode_refs))
    if key == "ratio":
        return Operand(ratio=_ratio(value, f"{path}.ratio", episode_refs))
    if key == "price":
        if value not in _PRICE_FIELDS:
            raise InvalidRequestError(f"{path}.price must be open, high, low or close")
        return Operand(price=str(value))
    if key == "const":
        return Operand(const=_number(value, f"{path}.const"))
    raise InvalidRequestError(f"{path} must carry exactly one of {_OPERAND_KEYS}")


def _compare(payload: Mapping[str, Any], path: str, episode_refs: frozenset[str] | None) -> Compare:
    op = payload.get("op")
    if op not in _COMPARE_OPS:
        raise InvalidRequestError(f"{path}.op must be one of >, >=, <, <=", op=op)
    left = _operand(payload.get("left"), f"{path}.left", episode_refs)
    right = _operand(payload.get("right"), f"{path}.right", episode_refs)
    if left.const is not None and right.const is not None:
        raise InvalidRequestError(f"{path} must compare at least one non-constant operand")
    return Compare(left, str(op), right)


def _change(payload: Mapping[str, Any], path: str, episode_refs: frozenset[str] | None) -> Change:
    operand = _operand(payload.get("operand"), f"{path}.operand", episode_refs)
    if operand.feature is None:
        raise InvalidRequestError(f"{path}.operand must be a feature reference")
    lookback = payload.get("lookback")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
        raise InvalidRequestError(f"{path}.lookback must be a positive integer", lookback=lookback)
    op = payload.get("op")
    if op not in _COMPARE_OPS:
        raise InvalidRequestError(f"{path}.op must be one of >, >=, <, <=", op=op)
    return Change(operand, int(lookback), str(op), _number(payload.get("value"), f"{path}.value"))


_RANGE_BOUNDS = frozenset({"inclusive", "exclusive"})
_RANGE_EMPTY = frozenset({"block", "pass"})


def _optional_bound(payload: Mapping[str, Any], key: str, path: str) -> float | None:
    if key not in payload:
        raise InvalidRequestError(f"{path}.{key} is required (a number or null)")
    value = payload[key]
    return None if value is None else _number(value, f"{path}.{key}")


def _range(payload: Mapping[str, Any], path: str, episode_refs: frozenset[str] | None) -> Range:
    operand = _operand(payload.get("operand"), f"{path}.operand", episode_refs)
    if operand.const is not None:
        raise InvalidRequestError(f"{path}.operand must be a feature, an episode or a price")
    low = _optional_bound(payload, "min", path)
    high = _optional_bound(payload, "max", path)
    bounds = payload.get("bounds", "inclusive")
    if bounds not in _RANGE_BOUNDS:
        raise InvalidRequestError(f"{path}.bounds must be inclusive or exclusive", bounds=bounds)
    empty = payload.get("empty", "block")
    if empty not in _RANGE_EMPTY:
        raise InvalidRequestError(f"{path}.empty must be block or pass", empty=empty)
    if (
        low is not None
        and high is not None
        and (low > high or (bounds == "exclusive" and low == high))
    ):
        raise InvalidRequestError(f"{path}.min must not exceed max")
    return Range(operand, low, high, str(bounds), str(empty))


_CLASS_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    # class -> (condition fields, fields a `short` override may replace)
    "compare": ({"left", "op", "right"}, {"left", "op", "right"}),
    "range": (
        {"operand", "min", "max", "bounds", "empty"},
        {"min", "max", "bounds", "empty"},
    ),
    "change": ({"operand", "lookback", "op", "value"}, {"op", "value"}),
}


def _check_episode_override(
    long: Condition, short: Condition, override: Mapping[str, Any], path: str
) -> None:
    """ema-stack-episode-v1: a `short` override never introduces an episode
    operand, and over an episode predicate it replaces only `op`, constant
    operands, `min` or `max` (the episode is read per side already)."""

    has_episode = any(operand_needs_episode(operand) for operand in _operands(long))
    for role, short_operand in zip(("left", "right"), _operands(short), strict=False):
        if role not in override:
            continue
        if operand_needs_episode(short_operand):
            raise InvalidRequestError(
                f"{path}.{role} must not be an episode, segment or ratio reference"
            )
        if has_episode and short_operand.const is None:
            raise InvalidRequestError(
                f"{path}.{role} of an episode predicate may only be a constant"
            )


_REGIMES = frozenset({"aligned", "countertrend", "neutral"})
_TEMPORAL_MODES = frozenset({"held_for", "within"})


def _state(
    payload: Mapping[str, Any], path: str, context_refs: Collection[str] | None
) -> StatePredicate:
    _only_fields(payload, {"kind", "context_ref", "in"}, path)
    context_ref = payload.get("context_ref")
    if not isinstance(context_ref, str) or not context_ref:
        raise InvalidRequestError(f"{path}.context_ref must be a non-empty string")
    if context_refs is not None and context_ref not in context_refs:
        raise InvalidRequestError(
            f"{path}.context_ref is not declared in contexts", context_ref=context_ref
        )
    regimes = payload.get("in")
    if (
        not isinstance(regimes, list)
        or not regimes
        or any(item not in _REGIMES for item in regimes)
        or len(set(regimes)) != len(regimes)
    ):
        raise InvalidRequestError(
            f"{path}.in must be a non-empty unique subset of aligned, countertrend, neutral"
        )
    return StatePredicate(context_ref, tuple(sorted(regimes)))


def _temporal(
    payload: Mapping[str, Any],
    path: str,
    context_refs: Collection[str] | None,
    episode_refs: Collection[str] | None,
) -> TemporalPredicate:
    _only_fields(payload, {"kind", "mode", "bars", "of"}, path)
    mode = payload.get("mode")
    if mode not in _TEMPORAL_MODES:
        raise InvalidRequestError(f"{path}.mode must be held_for or within", mode=mode)
    bars = payload.get("bars")
    if isinstance(bars, bool) or not isinstance(bars, int) or bars < 1:
        raise InvalidRequestError(f"{path}.bars must be a positive integer", bars=bars)
    inner = parse_predicate(
        payload.get("of"), f"{path}.of", context_refs=context_refs, episode_refs=episode_refs
    )
    if isinstance(inner, TemporalPredicate):
        raise InvalidRequestError(f"{path}.of must not be temporal")
    return TemporalPredicate(str(mode), bars, inner)


def parse_predicate(
    raw: object,
    path: str,
    *,
    context_refs: Collection[str] | None = None,
    episode_refs: Collection[str] | None = None,
) -> AnyPredicate:
    """Parse and validate one predicate object. Feature operands are
    validated by the canonical feature-kind contract, never here.
    `context_refs` / `episode_refs`: the spec's declared contexts and EMA
    stack episodes (None skips that check; evaluation then fails closed on
    an unknown one)."""

    payload = _mapping(raw, path)
    kind = payload.get("kind")
    if kind == "state":
        return _state(payload, path, context_refs)
    if kind == "temporal":
        return _temporal(payload, path, context_refs, episode_refs)
    if kind not in _CLASS_FIELDS:
        raise InvalidRequestError(
            f"{path}.kind must be compare, range, change, state or temporal", kind=kind
        )
    fields, overridable = _CLASS_FIELDS[kind]
    _only_fields(payload, {"kind", "short", *fields}, path)
    refs = frozenset(episode_refs) if episode_refs is not None else None
    parsers: dict[str, Callable[[Mapping[str, Any], str, frozenset[str] | None], Condition]] = {
        "compare": _compare,
        "range": _range,
        "change": _change,
    }
    parse = parsers[kind]
    long = parse(payload, path, refs)
    short: Condition | None = None
    if payload.get("short") is not None:
        override = _mapping(payload.get("short"), f"{path}.short")
        if not override:
            raise InvalidRequestError(f"{path}.short must not be empty")
        _only_fields(override, overridable, f"{path}.short")
        short = parse({**payload, **override}, f"{path}.short", refs)
        _check_episode_override(long, short, override, f"{path}.short")
    return Predicate(long, short)


# -- evaluation ---------------------------------------------------------------


def _column_array(frame: FeatureFrameLike, output_id: str) -> np.ndarray:
    """One plan column as a read-only float64 array, None and non-finite
    mapped to NaN (design D8)."""

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
    array.flags.writeable = False
    return array


def _feature_array(
    feature: PlannedFeature,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
) -> np.ndarray:
    column_ids = identity.column_ids if identity is not None else None
    label = feature.output_id
    return compute_through(
        context,
        column_ids.get(label) if column_ids is not None else None,
        functools.partial(_column_array, frame, label),
    )


def _values(
    operand: Operand,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
    path: str = "operand",
) -> np.ndarray | float:
    if operand.const is not None:
        return operand.const
    if operand.price is not None:
        return frame_market_arrays(frame).array(operand.price)
    if operand.episode is not None:
        episodes = bundle.episodes if bundle is not None else None
        if episodes is None:
            raise InvalidRequestError(
                "episode operand has no evaluated episode", episode_ref=operand.episode.ref
            )
        return compute_through(
            context,
            identity.episode_ids.get(operand.episode) if identity is not None else None,
            functools.partial(
                episode_operand_values, episodes.side(operand.episode.ref, side), operand.episode
            ),
        )
    node = identity.operand_ids.get(path) if identity is not None else None
    if operand.segment is not None:
        return compute_through(
            context,
            node,
            functools.partial(
                _segment_operand, operand.segment, frame, context, identity, side, bundle
            ),
        )
    if operand.ratio is not None:
        return compute_through(
            context,
            node,
            functools.partial(
                _ratio_operand, operand.ratio, frame, context, identity, side, bundle, path
            ),
        )
    assert operand.feature is not None
    return _feature_array(operand.feature, frame, context, identity)


def _segment_operand(
    segment: Segment,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "segment operand has no evaluated episode", episode_ref=segment.episode
        )
    base = frame.market.base_timeframe
    for feature in segment.series.features():
        if feature.timeframe not in ("base", base):
            raise InvalidRequestError(
                "segment series must be on the base timeframe",
                output_id=feature.output_id,
                timeframe=feature.timeframe,
            )
    if segment.series.by_side:
        series = _feature_array(segment.series.for_side(side), frame, context, identity)
    else:
        arrays = [_feature_array(f, frame, context, identity) for f in segment.series.features()]
        series = arrays[0] if len(arrays) == 1 else arrays[0] - arrays[1]
        if side == "short":
            series = -series
    return segment_values(episodes.side(segment.episode, side), series, segment)


def _ratio_operand(
    ratio: Ratio,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
    path: str,
) -> np.ndarray:
    length = len(frame.time_ms)
    left = np.broadcast_to(
        _values(ratio.left, frame, context, identity, side, bundle, f"{path}.left"), (length,)
    )
    right = np.broadcast_to(
        _values(ratio.right, frame, context, identity, side, bundle, f"{path}.right"), (length,)
    )
    valid = np.isfinite(left) & np.isfinite(right) & (right > ratio.right_floor)
    out = np.full(length, math.nan)
    np.divide(left, right, out=out, where=valid)
    out.flags.writeable = False
    return out


def _take_rows(column: np.ndarray, rows: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(len(rows), math.nan)
    out[mask] = column[rows[mask]]
    return out


def segment_values(episode: SideEpisode, series: np.ndarray, segment: Segment) -> np.ndarray:
    """The segment on every bar as a read-only float64 array (OpenSpec
    `a1-band-filter-v1`, design D2). `series` is already side-signed. The
    leg runs between two points of the touch row of the current touch
    `touch_number[t]`, both ends inclusive; only bars `<= t` are read. O(bars)
    through prefix sums."""

    size = len(series)
    state = episode.state
    touch_number = state["touch_number"]
    live = np.isfinite(touch_number)
    count = np.where(live, touch_number, 0.0)
    valid = live & (count >= 1)
    episode_id = np.where(live, state["episode_id"], 0.0).astype(np.int64)
    first = episode.first_row[np.clip(episode_id, 0, len(episode.first_row) - 1)]
    rows = np.where(valid, first + count.astype(np.int64) - 1, 0)
    points = {
        "origin": _take_rows(episode.touches["origin_bar"], rows, valid),
        "peak": _take_rows(episode.touches["peak_bar"], rows, valid),
        "current": np.arange(size, dtype=np.float64),
    }
    if segment.touch == "previous":
        # Same episode only: the first touch has no previous one.
        has_previous = valid & (count >= 2)
        earlier = np.where(has_previous, rows - 1, 0)
        begin = _take_rows(episode.touches["origin_bar"], earlier, has_previous)
        end = _take_rows(episode.touches["peak_bar"], earlier, has_previous)
    else:
        begin, end = points[segment.start], points[segment.end]
    with np.errstate(invalid="ignore"):
        ok = valid & np.isfinite(begin) & np.isfinite(end) & (begin <= end)
    a = np.where(ok, begin, 0).astype(np.int64)
    e = np.where(ok, end, 0).astype(np.int64)
    s = a if segment.last_n is None else np.maximum(a, e - segment.last_n + 1)

    finite = np.isfinite(series)
    bad = np.zeros(size + 1, dtype=np.int64)
    np.cumsum(~finite, out=bad[1:])
    clean = np.where(finite, series, 0.0)
    if segment.eligibility is not None:
        ok &= _eligible(segment.eligibility, points, valid, clean, bad)
    if segment.value == "from_start":
        result = _from_start_aggregate(segment, clean, bad, s, e, ok)
    elif segment.aggregate in _SEGMENT_CHANGE_AGGREGATES:
        result = _change_aggregate(segment, clean, bad, s, e, ok)
    else:
        if segment.value == "level":
            cumulative = np.zeros(size + 1)
            np.cumsum(clean, out=cumulative[1:])
            total = cumulative[e + 1] - cumulative[s]
            ok &= (bad[e + 1] - bad[s]) == 0
        else:
            before = s - 1
            ok &= before >= 0
            before = np.maximum(before, 0)
            total = clean[e] - clean[before]
            ok &= (bad[e + 1] - bad[before]) == 0
        result = total if segment.aggregate == "sum" else total / (e - s + 1)
        result = np.where(ok, result, math.nan)
    if segment.negate:
        result = -result
    out = np.where(ok & np.isfinite(result), result, math.nan)
    out.flags.writeable = False
    return out


def _from_start_aggregate(
    segment: Segment,
    clean: np.ndarray,
    bad: np.ndarray,
    s: np.ndarray,
    e: np.ndarray,
    ok: np.ndarray,
) -> np.ndarray:
    """`max`, `min`, `sum` or `mean_per_bar` of `x[u] - x[s]` over the window
    `s..e` (`b2-di-wave-v1`, design D3). A non-finite `x` in the window makes
    the value missing. `ok` is narrowed in place."""

    ok &= (bad[e + 1] - bad[s]) == 0
    result = np.full(len(clean), math.nan)
    rows = np.flatnonzero(ok)
    if not len(rows):
        return result
    low, high = s[rows], e[rows]
    start_level = clean[low]
    if segment.aggregate in ("max", "min"):
        level = _window_extreme(clean, low, high, segment.aggregate == "max")
    else:
        cumulative = np.zeros(len(clean) + 1)
        np.cumsum(clean, out=cumulative[1:])
        total = cumulative[high + 1] - cumulative[low]
        level = total if segment.aggregate == "sum" else total / (high - low + 1)
        if segment.aggregate == "sum":
            start_level = start_level * (high - low + 1)
    result[rows] = level - start_level
    return result


def _eligible(
    eligibility: Eligibility,
    points: dict[str, np.ndarray],
    valid: np.ndarray,
    clean: np.ndarray,
    bad: np.ndarray,
) -> np.ndarray:
    """Per bar: whether both legs of the current touch satisfy the eligibility
    (`a2-shape-aggregates-v1`, design D5), whatever leg the segment reads."""

    origin, peak, current = points["origin"], points["peak"], points["current"]
    with np.errstate(invalid="ignore"):
        ok = valid & np.isfinite(origin) & np.isfinite(peak) & (origin <= peak) & (peak <= current)
    o = np.where(ok, origin, 0).astype(np.int64)
    p = np.where(ok, peak, 0).astype(np.int64)
    t = np.where(ok, current, 0).astype(np.int64)
    if eligibility.pullback_min_bars is not None:
        ok &= t - p + 1 >= eligibility.pullback_min_bars
    if eligibility.legs_min_bars is not None:
        ok &= (p - o + 1 >= eligibility.legs_min_bars) & (t - p + 1 >= eligibility.legs_min_bars)
    window = eligibility.window
    if window is not None:
        impulse_start = np.maximum(o, p - window + 1) - 1
        pullback_start = np.maximum(p, t - window + 1) - 1
        ok &= (impulse_start >= 0) & (pullback_start >= 0)
        impulse_start = np.maximum(impulse_start, 0)
        pullback_start = np.maximum(pullback_start, 0)
        ok &= (bad[p + 1] - bad[impulse_start]) == 0
        ok &= (bad[t + 1] - bad[pullback_start]) == 0
        if eligibility.impulse_positive:
            ok &= (clean[p] - clean[impulse_start]) > 0
    return ok


def _change_aggregate(
    segment: Segment,
    clean: np.ndarray,
    bad: np.ndarray,
    s: np.ndarray,
    e: np.ndarray,
    ok: np.ndarray,
) -> np.ndarray:
    """`max`, `min`, `abs_sum` and `top_abs_sum` of the one-bar or `span`-bar
    changes of the series over the window `s..e` (`a2-shape-aggregates-v1`,
    design D2 and D3). `ok` is narrowed in place."""

    span = segment.span or 1
    size = len(clean)
    before = s - 1
    ok &= before >= 0
    before = np.maximum(before, 0)
    ok &= (bad[e + 1] - bad[before]) == 0
    first = s + span - 1
    ok &= first <= e
    changes = np.zeros(size)
    if span < size:
        changes[span:] = clean[span:] - clean[:-span]
    result = np.full(size, math.nan)
    rows = np.flatnonzero(ok)
    if not len(rows):
        return result
    low, high = first[rows], e[rows]
    if segment.aggregate in ("max", "min"):
        result[rows] = _window_extreme(changes, low, high, segment.aggregate == "max")
    elif segment.aggregate == "abs_sum":
        result[rows] = _abs_sum(changes, low, high)
    else:
        assert segment.top is not None and segment.last_n is not None
        top_sum = _window_top_sum(np.abs(changes), low, high, segment.top, segment.last_n)
        if segment.aggregate == "top_abs_sum":
            result[rows] = top_sum
        else:
            result[rows] = _normalized_share(
                top_sum, _abs_sum(changes, low, high), high - low + 1, segment.top
            )
    return result


def _abs_sum(changes: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    cumulative = np.zeros(len(changes) + 1)
    np.cumsum(np.abs(changes), out=cumulative[1:])
    return np.asarray(cumulative[high + 1] - cumulative[low])


def _normalized_share(
    top_sum: np.ndarray, total: np.ndarray, bars: np.ndarray, top: int
) -> np.ndarray:
    """`(share - top/N) / (1 - top/N)` of the top-`top` share of the absolute
    changes over `N` window bars: 0 for an even window, 1 for one made by `top`
    bars. Missing for a zero total or `N <= top` (`a2-shape-aggregates-v1`, D3)."""

    floor = top / bars
    with np.errstate(invalid="ignore", divide="ignore"):
        share = top_sum / total
        value = (share - floor) / (1.0 - floor)
    return np.where((total > 0) & (bars > top), value, math.nan)


def _window_extreme(
    values: np.ndarray, low: np.ndarray, high: np.ndarray, largest: bool
) -> np.ndarray:
    """max / min of `values[low..high]` per query by a sparse table whose
    depth is bounded by the longest window: O(n log n) build, O(1) per query."""

    reduce = np.maximum if largest else np.minimum
    length = high - low + 1
    depth = int(np.log2(length.max())) if len(length) else 0
    levels = [values]
    for j in range(1, depth + 1):
        previous = levels[-1]
        half = 1 << (j - 1)
        levels.append(reduce(previous[:-half], previous[half:]))
    level = np.floor(np.log2(length)).astype(np.int64)
    out = np.empty(len(low))
    for j in np.unique(level):
        pick = level == j
        table = levels[int(j)]
        out[pick] = reduce(table[low[pick]], table[high[pick] - (1 << int(j)) + 1])
    return out


def _window_top_sum(
    absolute: np.ndarray, low: np.ndarray, high: np.ndarray, top: int, last_n: int
) -> np.ndarray:
    """Sum of the `top` largest `absolute[low..high]` per query (all of them when
    fewer), in chunks so memory stays bounded; cost O(queries * last_n)."""

    out = np.empty(len(low))
    offsets = np.arange(last_n)
    for start in range(0, len(low), 8192):
        lo = low[start : start + 8192]
        hi = high[start : start + 8192]
        index = hi[:, None] - offsets[None, :]
        inside = index >= lo[:, None]
        gathered = np.where(inside, absolute[np.maximum(index, 0)], 0.0)
        gathered.sort(axis=1)
        out[start : start + 8192] = gathered[:, -top:].sum(axis=1)
    return out


def predicate_value(
    predicate: AnyPredicate,
    frame: FeatureFrameLike,
    side: str,
    *,
    context: EvaluationContext | None = None,
    identity: PredicateIdentity | None = None,
    bundle: ContextBundle | None = None,
) -> np.ndarray | None:
    """The operand value of a `range` over a segment or a ratio, for the
    evidence trace (design D6); None for every other predicate."""

    if not isinstance(predicate, Predicate):
        return None
    condition = predicate.for_side(side)
    if not (
        isinstance(condition, Range)
        and (condition.operand.segment is not None or condition.operand.ratio is not None)
    ):
        return None
    value = _values(condition.operand, frame, context, identity, side, bundle, "operand")
    assert isinstance(value, np.ndarray)
    return value


def _finite(values: np.ndarray | float) -> np.ndarray | bool:
    return np.isfinite(values)


def _feature_bar_ratio(feature: PlannedFeature, frame: FeatureFrameLike) -> int:
    """Base rows per bar of the feature's own timeframe. A `MarketFrame` is a
    complete gapless grid, so a shift by `lookback * ratio` rows is a shift by
    `lookback` whole bars of the feature's series (design D2)."""

    if feature.timeframe == "base":
        return 1
    bar_ms = timeframe_duration_ms(feature.timeframe)
    base_ms = timeframe_duration_ms(frame.market.base_timeframe)
    if bar_ms % base_ms:
        raise InvalidRequestError(
            "change operand timeframe must be an integral multiple of the base timeframe",
            timeframe=feature.timeframe,
            base_timeframe=frame.market.base_timeframe,
        )
    return bar_ms // base_ms


def _evaluate_condition(
    condition: Condition,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    length = len(frame.time_ms)
    if isinstance(condition, Compare):
        left = _values(condition.left, frame, context, identity, side, bundle, "left")
        right = _values(condition.right, frame, context, identity, side, bundle, "right")
        result = _finite(left) & _finite(right) & _COMPARE_OPS[condition.op](left, right)
    elif isinstance(condition, Change):
        assert condition.operand.feature is not None
        current = _values(condition.operand, frame, context, identity, side, bundle)
        assert isinstance(current, np.ndarray)
        shift = condition.lookback * _feature_bar_ratio(condition.operand.feature, frame)
        earlier = np.full(length, np.nan)
        if shift < length:
            earlier[shift:] = current[: length - shift]
        with np.errstate(invalid="ignore"):
            result = (
                np.isfinite(current)
                & np.isfinite(earlier)
                & _COMPARE_OPS[condition.op](current - earlier, condition.value)
            )
    else:
        value = _values(condition.operand, frame, context, identity, side, bundle)
        result = _range_mask(condition, value)
    mask = np.broadcast_to(np.asarray(result, dtype=bool), (length,)).copy()
    mask.flags.writeable = False
    return mask


def _range_mask(condition: Range, value: np.ndarray | float) -> np.ndarray:
    """A set side imposes its comparison on a finite value; a missing side
    imposes nothing. A non-finite value follows `empty` (design D4)."""

    finite = np.asarray(_finite(value), dtype=bool)
    exclusive = condition.bounds == "exclusive"
    ok = finite.copy()
    if condition.min is not None:
        ok &= (value > condition.min) if exclusive else (value >= condition.min)
    if condition.max is not None:
        ok &= (value < condition.max) if exclusive else (value <= condition.max)
    return ok | ~finite if condition.empty == "pass" else ok


def _state_mask(
    predicate: StatePredicate, frame: FeatureFrameLike, side: str, bundle: ContextBundle | None
) -> np.ndarray:
    from strategy_engine.strategies.ema_pullback.context_consumption import resolve_htf_regime

    output = next(
        (
            item
            for item in (bundle.outputs if bundle else ())
            if item.context_ref == predicate.context_ref
        ),
        None,
    )
    if output is None:
        raise InvalidRequestError(
            "state predicate context is not evaluated", context_ref=predicate.context_ref
        )
    mask = np.zeros(len(frame.time_ms), dtype=bool)
    for raw_state, raw_mask in (
        ("up", output.up),
        ("down", output.down),
        ("neutral", output.neutral),
    ):
        if resolve_htf_regime(raw_state, side) in predicate.regimes:
            mask |= np.asarray(raw_mask, dtype=bool)
    mask.flags.writeable = False
    return mask


def _window_mask(mode: str, bars: int, inner: np.ndarray) -> np.ndarray:
    """O(n) in the number of bars, independent of `bars`: the count of true
    bars in each trailing window from a cumulative sum and a shifted
    difference. `held_for` needs a full window of `bars` true bars (False
    while fewer bars exist); `within` uses the shortened initial window."""

    length = len(inner)
    cumulative = np.zeros(length + 1, dtype=np.int64)
    np.cumsum(inner, out=cumulative[1:])
    starts = np.maximum(np.arange(1, length + 1) - bars, 0)
    counts = cumulative[1:] - cumulative[starts]
    mask = counts == bars if mode == "held_for" else counts > 0
    mask.flags.writeable = False
    return mask


def _evaluate(
    predicate: AnyPredicate,
    frame: FeatureFrameLike,
    side: str,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    bundle: ContextBundle | None,
) -> np.ndarray:
    if isinstance(predicate, Predicate):
        return _evaluate_condition(predicate.for_side(side), frame, context, identity, side, bundle)
    if isinstance(predicate, StatePredicate):
        return _state_mask(predicate, frame, side, bundle)
    inner = evaluate_predicate(
        predicate.of,
        frame,
        side,
        context=context,
        identity=identity.inner if identity is not None else None,
        bundle=bundle,
    )
    return _window_mask(predicate.mode, predicate.bars, inner)


def evaluate_predicate(
    predicate: AnyPredicate,
    frame: FeatureFrameLike,
    side: str,
    *,
    context: EvaluationContext | None = None,
    identity: PredicateIdentity | None = None,
    bundle: ContextBundle | None = None,
) -> np.ndarray:
    """The predicate's read-only bool mask on the base timeline for `side`.
    Non-finite operands are False (design D5)."""

    if side not in _SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    return compute_through(
        context,
        identity.local if identity is not None else None,
        functools.partial(_evaluate, predicate, frame, side, context, identity, bundle),
    )


# -- identity (design D10) ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class PredicateIdentity:
    """`local` is the predicate node for one side. `nested` are the nodes
    its compute consumes (column arrays; for a temporal predicate its inner
    predicate and that one's nested nodes), predicted by the memo pre-pass
    once per `local` consumption, like the width prefix."""

    local: NodeSpec
    nested: tuple[NodeSpec, ...] = ()
    column_ids: Mapping[str, NodeSpec] = field(default_factory=dict)
    inner: PredicateIdentity | None = None
    episode_ids: Mapping[EpisodeRef, NodeSpec] = field(default_factory=dict)
    # Segment and ratio operand nodes by operand path (`operand`, `left`,
    # `right`, `<path>.left`, ...) and, for a range over one of them, the
    # node whose value feeds the evidence trace (design D5, D6).
    operand_ids: Mapping[str, NodeSpec] = field(default_factory=dict)
    value_node: NodeSpec | None = None


def column_node(feature: NodeSpec) -> NodeSpec:
    return node_spec(
        "predicate.column", version=PREDICATE_NODE_VERSION, upstream={"feature": feature}
    )


def episode_operand_node(episode: NodeSpec, operand: EpisodeRef) -> NodeSpec:
    """One episode operand: its `entity`, `index` and `field` over the
    episode node of the evaluated side (the `ref` label is not identity)."""

    entity, index, field_name = operand.identity_params()
    return node_spec(
        "predicate.episode_operand",
        version=PREDICATE_NODE_VERSION,
        params={"entity": entity, "index": index, "field": field_name},
        upstream={"episode": episode},
    )


def _operand_param(operand: Operand) -> tuple[object, ...]:
    if operand.const is not None:
        return ("const", operand.const)
    if operand.price is not None:
        return ("price", operand.price)
    if operand.episode is not None:
        return ("episode",)
    if operand.segment is not None:
        return ("segment",)
    if operand.ratio is not None:
        return ("ratio",)
    return ("feature",)


def resolve_predicate(
    predicate: AnyPredicate,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
    contexts: Mapping[str, NodeSpec] | None = None,
) -> PredicateIdentity:
    """Identity twin of `evaluate_predicate`. A `compare`/`range` without a
    `short` override is side-free: its identity carries no side and is
    shared by both sides. `state` carries the side; `temporal` inherits its
    inner predicate's."""

    if side not in _SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    if isinstance(predicate, StatePredicate):
        context = (contexts or {}).get(predicate.context_ref)
        if context is None:
            raise InvalidRequestError(
                "state predicate context is not declared", context_ref=predicate.context_ref
            )
        return PredicateIdentity(
            node_spec(
                "predicate.state",
                version=PREDICATE_NODE_VERSION,
                params={"in": predicate.regimes},
                upstream={"context": context},
                side=side,
            )
        )
    if isinstance(predicate, TemporalPredicate):
        inner = resolve_predicate(predicate.of, feature_ids, side, contexts)
        return PredicateIdentity(
            node_spec(
                "predicate.temporal",
                version=PREDICATE_NODE_VERSION,
                params={"mode": predicate.mode, "bars": predicate.bars},
                upstream={"of": inner.local},
                side=inner.local.side,
            ),
            nested=(inner.local, *inner.nested),
            inner=inner,
        )
    condition = predicate.for_side(side)
    upstream: dict[str, NodeSpec] = {}
    columns: list[NodeSpec] = []
    column_ids: dict[str, NodeSpec] = {}
    episode_ids: dict[EpisodeRef, NodeSpec] = {}
    operand_ids: dict[str, NodeSpec] = {}
    roles = ("left", "right") if isinstance(condition, Compare) else ("operand",)
    for role, operand in zip(roles, _operands(condition), strict=True):
        node, consumed = _resolve_operand(
            operand, role, feature_ids, side, contexts, column_ids, episode_ids, operand_ids
        )
        if node is not None:
            upstream[role] = node
            columns.extend(consumed)
    if isinstance(condition, Compare):
        kind = "predicate.compare"
        params: dict[str, object] = {
            "op": condition.op,
            "left": _operand_param(condition.left),
            "right": _operand_param(condition.right),
        }
    elif isinstance(condition, Change):
        kind = "predicate.change"
        params = {"op": condition.op, "value": condition.value, "lookback": condition.lookback}
    else:
        kind = "predicate.range"
        params = {
            "operand": _operand_param(condition.operand),
            "min": condition.min,
            "max": condition.max,
        }
        # Non-default only, so every range written before a1-band-filter-v1
        # keeps its identity.
        if condition.bounds != "inclusive":
            params["bounds"] = condition.bounds
        if condition.empty != "block":
            params["empty"] = condition.empty
    local = node_spec(
        kind,
        version=PREDICATE_NODE_VERSION,
        params=params,
        upstream=upstream,
        side=side
        if predicate.short is not None
        or any(operand_needs_episode(item) for item in _operands(condition))
        else None,
    )
    value_node = (
        operand_ids.get("operand")
        if isinstance(condition, Range)
        and (condition.operand.segment is not None or condition.operand.ratio is not None)
        else None
    )
    return PredicateIdentity(
        local,
        tuple(columns),
        column_ids,
        episode_ids=episode_ids,
        operand_ids=operand_ids,
        value_node=value_node,
    )


def _resolve_operand(
    operand: Operand,
    path: str,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
    contexts: Mapping[str, NodeSpec] | None,
    column_ids: dict[str, NodeSpec],
    episode_ids: dict[EpisodeRef, NodeSpec],
    operand_ids: dict[str, NodeSpec],
) -> tuple[NodeSpec | None, list[NodeSpec]]:
    """Identity twin of `_values` for one operand: the node it contributes as
    upstream of its parent (None for a price or a constant) and the nodes its
    evaluation consumes, in order, the operand's own node first."""

    if operand.episode is not None:
        episode = (contexts or {}).get(episode_identity_key(operand.episode.ref, side))
        if episode is None:
            raise InvalidRequestError(
                "episode operand is not declared", episode_ref=operand.episode.ref
            )
        node = episode_operand_node(episode, operand.episode)
        episode_ids[operand.episode] = node
        return node, [node]
    if operand.feature is not None:
        column = _column_identity(operand.feature, feature_ids, column_ids)
        return column, [column]
    if operand.segment is not None:
        segment = operand.segment
        episode = (contexts or {}).get(episode_identity_key(segment.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "segment episode is not declared", episode_ref=segment.episode
            )
        upstream: dict[str, NodeSpec] = {"episode": episode}
        consumed: list[NodeSpec] = []
        read = (
            (segment.series.for_side(side),)
            if segment.series.by_side
            else segment.series.features()
        )
        for role, feature in zip(("left", "right"), read, strict=False):
            column = _column_identity(feature, feature_ids, column_ids)
            upstream[role] = column
            consumed.append(column)
        segment_params: dict[str, Any] = {
            "from": segment.start,
            "to": segment.end,
            "value": segment.value,
            "window": segment.last_n,
            "aggregate": segment.aggregate,
            "negate": segment.negate,
        }
        if segment.span is not None:
            segment_params["span"] = segment.span
        if segment.touch != "current":
            segment_params["touch"] = segment.touch
        if segment.series.by_side:
            segment_params["by_side"] = True
        if segment.top is not None:
            segment_params["top"] = segment.top
        if segment.eligibility is not None:
            eligibility = segment.eligibility
            segment_params["eligibility"] = (
                eligibility.legs_min_bars,
                eligibility.window,
                eligibility.impulse_positive,
                eligibility.pullback_min_bars,
            )
        node = node_spec(
            "predicate.segment",
            version=PREDICATE_NODE_VERSION,
            params=segment_params,
            upstream=upstream,
            side=side,
        )
        operand_ids[path] = node
        return node, [node, *consumed]
    if operand.ratio is not None:
        ratio = operand.ratio
        upstream = {}
        consumed = []
        for role, child in (("left", ratio.left), ("right", ratio.right)):
            child_node, child_consumed = _resolve_operand(
                child,
                f"{path}.{role}",
                feature_ids,
                side,
                contexts,
                column_ids,
                episode_ids,
                operand_ids,
            )
            if child_node is not None:
                upstream[role] = child_node
                consumed.extend(child_consumed)
        ratio_params: dict[str, object] = {
            "left": _operand_param(ratio.left),
            "right": _operand_param(ratio.right),
        }
        if ratio.right_floor:
            ratio_params["right_floor"] = ratio.right_floor
        node = node_spec(
            "predicate.ratio",
            version=PREDICATE_NODE_VERSION,
            params=ratio_params,
            upstream=upstream,
            side=side if operand_needs_episode(operand) else None,
        )
        operand_ids[path] = node
        return node, [node, *consumed]
    return None, []


def _column_identity(
    feature: PlannedFeature,
    feature_ids: Mapping[str, NodeSpec],
    column_ids: dict[str, NodeSpec],
) -> NodeSpec:
    label = feature.output_id
    try:
        node = feature_ids[label]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=label) from exc
    column = column_node(node)
    column_ids[label] = column
    return column
