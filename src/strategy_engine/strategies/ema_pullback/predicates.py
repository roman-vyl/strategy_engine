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
from strategy_engine.strategies.ema_pullback.anchor_follow import anchor_follow_values
from strategy_engine.strategies.ema_pullback.candles import (
    CANDLE_ATR_FIELD,
    CANDLE_ATR_KIND,
    candle_values,
)
from strategy_engine.strategies.ema_pullback.completed_candle import (
    COMPLETED_CANDLE_ATR_FIELD,
    COMPLETED_CANDLE_ATR_KIND,
    COMPLETED_CANDLE_FIELDS,
    completed_candle_values,
)
from strategy_engine.strategies.ema_pullback.forming_candle import (
    FORMING_CANDLE_ATR_FIELD,
    FORMING_CANDLE_ATR_KIND,
    forming_candle_values,
)
from strategy_engine.strategies.ema_pullback.impulse_atr import (
    IMPULSE_ATR_FIELD,
    IMPULSE_ATR_KIND,
    impulse_atr_values,
)
from strategy_engine.strategies.ema_pullback.leg_efficiency import leg_efficiency_values
from strategy_engine.strategies.ema_pullback.leg_means import (
    FORCE_FIELDS,
    LEG_MEAN_FIELDS,
    LEG_SUM_FIELDS,
    LEG_TOP_MEAN_FIELDS,
    OWN_COLOR_VOLUME,
    force_series,
    leg_mean_values,
    leg_sum_values,
    leg_top_mean_values,
    own_color_volume_series,
)
from strategy_engine.strategies.ema_pullback.leg_speed import leg_bars_values, leg_speed_values
from strategy_engine.strategies.ema_pullback.pullback_depth import pullback_depth_values
from strategy_engine.strategies.ema_pullback.stack_episode import (
    EpisodeRef,
    SideEpisode,
    episode_identity_key,
    episode_operand_values,
    parse_episode_ref,
)
from strategy_engine.strategies.ema_pullback.window_extreme import window_extreme

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
class Candle:
    """The largest body, with or against the trade, over the `timeframe`
    candles that the bars of a leg of the current touch build, each divided by
    the ATR of its own candle (`b1-candle-ratio-v1`, design D1)."""

    episode: str
    leg: str
    timeframe: str
    direction: str
    atr: PlannedFeature | None = None


@dataclass(frozen=True, slots=True)
class LegMean:
    """The mean of a base-bar market field over the impulse `[S*, P]` or the
    pullback `[P+1, t]` of the current touch (`v1-volume-ratio-v1`, D1)."""

    episode: str
    leg: str
    field: str


@dataclass(frozen=True, slots=True)
class LegSum:
    """The sum of a base-bar market field over the impulse `[S*, P]` or the
    pullback `[P+1, t]` of the current touch (`v1-volume-sum-ratio-v1`, D1)."""

    episode: str
    leg: str
    field: str


@dataclass(frozen=True, slots=True)
class LegTopMean:
    """The mean of the largest `share` of a base-bar field over the impulse
    `[S*, P]` or the pullback `[P+1, t]` of the current touch
    (`v1-top-volume-ratio-v1`, D1)."""

    episode: str
    leg: str
    field: str
    share: float


@dataclass(frozen=True, slots=True)
class AnchorFollow:
    """The share of the gap between the peak price and the anchor EMA at the
    peak that the EMA closed by the evaluated bar (`c5-anchor-follow-v1`, D1)."""

    episode: str


@dataclass(frozen=True, slots=True)
class LegSpeed:
    """The price distance per bar of the impulse `[S*, P]` or the pullback
    `[P, t]` of the current touch (`a3-leg-speed-ratio-v1`, D1)."""

    episode: str
    leg: str


@dataclass(frozen=True, slots=True)
class ImpulseAtr:
    """The impulse height `|P - S*|` of the current touch over a rolling-mean
    ATR read on the peak bar (`b3-impulse-atr-v1`, D1)."""

    episode: str
    atr: PlannedFeature


@dataclass(frozen=True, slots=True)
class FormingCandle:
    """The move of the forming candle of `timeframe` from its open to the
    close of the evaluated bar over the Wilder ATR of the last completed
    candle, signed by the side (`d1-forming-candle-v1`, D1)."""

    episode: str
    timeframe: str
    atr: PlannedFeature


@dataclass(frozen=True, slots=True)
class CompletedCandle:
    """The body over the Wilder ATR of the candle before it, or the close
    position in the range, of the last completed candle of `timeframe`,
    signed by the side (`completed-candle-v1`, D1)."""

    episode: str
    timeframe: str
    field: str
    atr: PlannedFeature


@dataclass(frozen=True, slots=True)
class LegEfficiency:
    """The Kaufman efficiency ratio of the closes of the impulse `[S*, P]`
    or the pullback `[P, t]` of the current touch
    (`a5-leg-efficiency-ratio-v1`, D1)."""

    episode: str
    leg: str


@dataclass(frozen=True, slots=True)
class LegBars:
    """The number of base bars of the impulse `[S*, P]` or the pullback
    `[P, t]` of the current touch (`a4-leg-bars-ratio-v1`, D1)."""

    episode: str
    leg: str


@dataclass(frozen=True, slots=True)
class PullbackDepth:
    """The share of the impulse height `|P - S*|` that the pullback `[P, t]`
    of the current touch gave back, by its extreme price
    (`c3-pullback-depth-share-v1`, D1); `touch` previous gives the same share
    of the previous pullback `[P0, S*]` (`c3-previous-depth-ratio-v1`, D1)."""

    episode: str
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
    candle: Candle | None = None
    leg_mean: LegMean | None = None
    leg_sum: LegSum | None = None
    leg_top_mean: LegTopMean | None = None
    anchor_follow: AnchorFollow | None = None
    pullback_depth: PullbackDepth | None = None
    leg_speed: LegSpeed | None = None
    impulse_atr: ImpulseAtr | None = None
    leg_bars: LegBars | None = None
    forming_candle: FormingCandle | None = None
    leg_efficiency: LegEfficiency | None = None
    completed_candle: CompletedCandle | None = None


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
    if operand.candle is not None:
        return () if operand.candle.atr is None else (operand.candle.atr,)
    if operand.impulse_atr is not None:
        return (operand.impulse_atr.atr,)
    if operand.forming_candle is not None:
        return (operand.forming_candle.atr,)
    if operand.completed_candle is not None:
        return (operand.completed_candle.atr,)
    if operand.ratio is not None:
        return (*operand_features(operand.ratio.left), *operand_features(operand.ratio.right))
    return ()


def operand_needs_episode(operand: Operand) -> bool:
    """True iff the operand reads the EMA stack episode bundle."""

    if (
        operand.episode is not None
        or operand.segment is not None
        or operand.candle is not None
        or operand.leg_mean is not None
        or operand.leg_sum is not None
        or operand.leg_top_mean is not None
        or operand.anchor_follow is not None
        or operand.pullback_depth is not None
        or operand.leg_speed is not None
        or operand.impulse_atr is not None
        or operand.leg_bars is not None
        or operand.forming_candle is not None
        or operand.leg_efficiency is not None
        or operand.completed_candle is not None
    ):
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


_OPERAND_KEYS = (
    "feature, episode, segment, candle, leg_mean, leg_sum, leg_top_mean, anchor_follow, "
    "pullback_depth, leg_speed, impulse_atr, leg_bars, forming_candle, leg_efficiency, "
    "completed_candle, ratio, price or const"
)
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
_SEGMENT_SPANS = frozenset(
    {
        ("origin", "peak"),
        ("peak", "current"),
        ("origin", "current"),
        ("peak", "touch"),
        ("peak", "next_origin"),
    }
)
_PREVIOUS_SPANS = frozenset({("origin", "peak"), ("peak", "next_origin")})
_TOUCH_COLUMNS = {"origin": "origin_bar", "peak": "peak_bar"}
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
            f"{path}.from/to must be origin-peak, peak-current, origin-current, "
            "peak-touch or peak-next_origin",
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
    if touch == "previous" and (start, end) not in _PREVIOUS_SPANS:
        raise InvalidRequestError(
            f"{path}.touch previous needs origin to peak or peak to next_origin"
        )
    if end == "next_origin" and touch != "previous":
        raise InvalidRequestError(f"{path}.to next_origin needs touch previous")
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


_CANDLE_FIELDS = {"episode", "leg", "timeframe", "direction", CANDLE_ATR_FIELD}


def _candle(raw: object, path: str, episode_refs: frozenset[str] | None) -> Candle:
    payload = _mapping(raw, path)
    _only_fields(payload, _CANDLE_FIELDS, path)
    for key in ("episode", "leg", "timeframe", "direction"):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    leg, direction = payload["leg"], payload["direction"]
    if leg not in ("impulse", "pullback"):
        raise InvalidRequestError(f"{path}.leg must be impulse or pullback", leg=leg)
    if direction not in ("with", "against"):
        raise InvalidRequestError(f"{path}.direction must be with or against", direction=direction)
    timeframe = payload["timeframe"]
    if not isinstance(timeframe, str) or not timeframe or timeframe == "base":
        raise InvalidRequestError(f"{path}.timeframe must be a timeframe such as 15m")
    timeframe_duration_ms(timeframe)
    atr: PlannedFeature | None = None
    if payload.get(CANDLE_ATR_FIELD) is not None:
        atr = _feature(payload[CANDLE_ATR_FIELD], f"{path}.{CANDLE_ATR_FIELD}")
        if atr.kind != CANDLE_ATR_KIND:
            raise InvalidRequestError(f"{path}.atr must be the candle ATR feature", kind=atr.kind)
        if atr.timeframe != timeframe:
            raise InvalidRequestError(
                f"{path}.atr.timeframe must equal the candle timeframe",
                atr_timeframe=atr.timeframe,
                timeframe=timeframe,
            )
    return Candle(ref, str(leg), timeframe, str(direction), atr)


def _leg_mean(raw: object, path: str, episode_refs: frozenset[str] | None) -> LegMean:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", "leg", "field"}, path)
    for key in ("episode", "leg", "field"):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    leg, field = payload["leg"], payload["field"]
    if leg not in ("impulse", "pullback"):
        raise InvalidRequestError(f"{path}.leg must be impulse or pullback", leg=leg)
    if field not in LEG_MEAN_FIELDS:
        raise InvalidRequestError(f"{path}.field must be one of {LEG_MEAN_FIELDS}", field=field)
    return LegMean(ref, str(leg), str(field))


def _leg_sum(raw: object, path: str, episode_refs: frozenset[str] | None) -> LegSum:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", "leg", "field"}, path)
    for key in ("episode", "leg", "field"):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    leg, field = payload["leg"], payload["field"]
    if leg not in ("impulse", "pullback"):
        raise InvalidRequestError(f"{path}.leg must be impulse or pullback", leg=leg)
    if field not in LEG_SUM_FIELDS:
        raise InvalidRequestError(f"{path}.field must be one of {LEG_SUM_FIELDS}", field=field)
    return LegSum(ref, str(leg), str(field))


def _leg_top_mean(raw: object, path: str, episode_refs: frozenset[str] | None) -> LegTopMean:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", "leg", "field", "share"}, path)
    for key in ("episode", "leg", "field", "share"):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    leg, field = payload["leg"], payload["field"]
    if leg not in ("impulse", "pullback"):
        raise InvalidRequestError(f"{path}.leg must be impulse or pullback", leg=leg)
    if field not in LEG_TOP_MEAN_FIELDS:
        raise InvalidRequestError(f"{path}.field must be one of {LEG_TOP_MEAN_FIELDS}", field=field)
    share = _number(payload["share"], f"{path}.share")
    if not 0.0 < share <= 1.0:
        raise InvalidRequestError(f"{path}.share must be in (0, 1]", share=share)
    return LegTopMean(ref, str(leg), str(field), share)


def _anchor_follow(raw: object, path: str, episode_refs: frozenset[str] | None) -> AnchorFollow:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode"}, path)
    if "episode" not in payload:
        raise InvalidRequestError(f"{path}.episode is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    return AnchorFollow(ref)


def _pullback_depth(raw: object, path: str, episode_refs: frozenset[str] | None) -> PullbackDepth:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", "touch"}, path)
    if "episode" not in payload:
        raise InvalidRequestError(f"{path}.episode is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    touch = payload.get("touch", "current")
    if touch not in ("current", "previous"):
        raise InvalidRequestError(f"{path}.touch must be current or previous", touch=touch)
    return PullbackDepth(ref, str(touch))


def _leg_speed(raw: object, path: str, episode_refs: frozenset[str] | None) -> LegSpeed:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", "leg"}, path)
    for key in ("episode", "leg"):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    leg = payload["leg"]
    if leg not in ("impulse", "pullback"):
        raise InvalidRequestError(f"{path}.leg must be impulse or pullback", leg=leg)
    return LegSpeed(ref, str(leg))


def _leg_efficiency(raw: object, path: str, episode_refs: frozenset[str] | None) -> LegEfficiency:
    speed = _leg_speed(raw, path, episode_refs)
    return LegEfficiency(speed.episode, speed.leg)


def _leg_bars(raw: object, path: str, episode_refs: frozenset[str] | None) -> LegBars:
    speed = _leg_speed(raw, path, episode_refs)
    return LegBars(speed.episode, speed.leg)


def _impulse_atr(raw: object, path: str, episode_refs: frozenset[str] | None) -> ImpulseAtr:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", IMPULSE_ATR_FIELD}, path)
    for key in ("episode", IMPULSE_ATR_FIELD):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    atr = _feature(payload[IMPULSE_ATR_FIELD], f"{path}.{IMPULSE_ATR_FIELD}")
    if atr.kind != IMPULSE_ATR_KIND:
        raise InvalidRequestError(f"{path}.atr must be a feature of kind atr", kind=atr.kind)
    if atr.timeframe != "base":
        raise InvalidRequestError(
            f"{path}.atr must be on the base timeframe", timeframe=atr.timeframe
        )
    return ImpulseAtr(ref, atr)


def _forming_candle(raw: object, path: str, episode_refs: frozenset[str] | None) -> FormingCandle:
    payload = _mapping(raw, path)
    _only_fields(payload, {"episode", "timeframe", FORMING_CANDLE_ATR_FIELD}, path)
    for key in ("episode", "timeframe", FORMING_CANDLE_ATR_FIELD):
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    timeframe = payload["timeframe"]
    if not isinstance(timeframe, str) or not timeframe or timeframe == "base":
        raise InvalidRequestError(f"{path}.timeframe must be a timeframe such as 1d")
    timeframe_duration_ms(timeframe)
    atr = _feature(payload[FORMING_CANDLE_ATR_FIELD], f"{path}.{FORMING_CANDLE_ATR_FIELD}")
    if atr.kind != FORMING_CANDLE_ATR_KIND:
        raise InvalidRequestError(f"{path}.atr must be the candle ATR feature", kind=atr.kind)
    if atr.timeframe != timeframe:
        raise InvalidRequestError(
            f"{path}.atr.timeframe must equal the candle timeframe",
            atr_timeframe=atr.timeframe,
            timeframe=timeframe,
        )
    return FormingCandle(ref, timeframe, atr)


def _completed_candle(
    raw: object, path: str, episode_refs: frozenset[str] | None
) -> CompletedCandle:
    payload = _mapping(raw, path)
    keys = ("episode", "timeframe", "field", COMPLETED_CANDLE_ATR_FIELD)
    _only_fields(payload, set(keys), path)
    for key in keys:
        if key not in payload:
            raise InvalidRequestError(f"{path}.{key} is required")
    ref = payload["episode"]
    if not isinstance(ref, str) or not ref:
        raise InvalidRequestError(f"{path}.episode must be a non-empty string")
    if episode_refs is not None and ref not in episode_refs:
        raise InvalidRequestError(f"{path}.episode is not declared in ema_stack_episode", ref=ref)
    timeframe = payload["timeframe"]
    if not isinstance(timeframe, str) or not timeframe or timeframe == "base":
        raise InvalidRequestError(f"{path}.timeframe must be a timeframe such as 1d or 1w")
    timeframe_duration_ms(timeframe)
    field = payload["field"]
    if field not in COMPLETED_CANDLE_FIELDS:
        raise InvalidRequestError(f"{path}.field must be body or close_position", field=field)
    atr = _feature(payload[COMPLETED_CANDLE_ATR_FIELD], f"{path}.{COMPLETED_CANDLE_ATR_FIELD}")
    if atr.kind != COMPLETED_CANDLE_ATR_KIND:
        raise InvalidRequestError(f"{path}.atr must be the candle ATR feature", kind=atr.kind)
    if atr.timeframe != timeframe:
        raise InvalidRequestError(
            f"{path}.atr.timeframe must equal the candle timeframe",
            atr_timeframe=atr.timeframe,
            timeframe=timeframe,
        )
    return CompletedCandle(ref, timeframe, str(field), atr)


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
    if key == "candle":
        return Operand(candle=_candle(value, f"{path}.candle", episode_refs))
    if key == "leg_mean":
        return Operand(leg_mean=_leg_mean(value, f"{path}.leg_mean", episode_refs))
    if key == "leg_sum":
        return Operand(leg_sum=_leg_sum(value, f"{path}.leg_sum", episode_refs))
    if key == "leg_top_mean":
        return Operand(leg_top_mean=_leg_top_mean(value, f"{path}.leg_top_mean", episode_refs))
    if key == "anchor_follow":
        return Operand(anchor_follow=_anchor_follow(value, f"{path}.anchor_follow", episode_refs))
    if key == "pullback_depth":
        return Operand(
            pullback_depth=_pullback_depth(value, f"{path}.pullback_depth", episode_refs)
        )
    if key == "leg_speed":
        return Operand(leg_speed=_leg_speed(value, f"{path}.leg_speed", episode_refs))
    if key == "leg_efficiency":
        return Operand(
            leg_efficiency=_leg_efficiency(value, f"{path}.leg_efficiency", episode_refs)
        )
    if key == "leg_bars":
        return Operand(leg_bars=_leg_bars(value, f"{path}.leg_bars", episode_refs))
    if key == "forming_candle":
        return Operand(
            forming_candle=_forming_candle(value, f"{path}.forming_candle", episode_refs)
        )
    if key == "completed_candle":
        return Operand(
            completed_candle=_completed_candle(value, f"{path}.completed_candle", episode_refs)
        )
    if key == "impulse_atr":
        return Operand(impulse_atr=_impulse_atr(value, f"{path}.impulse_atr", episode_refs))
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
    if operand.candle is not None:
        return compute_through(
            context,
            node,
            functools.partial(
                _candle_operand, operand.candle, frame, context, identity, side, bundle
            ),
        )
    if operand.leg_mean is not None:
        return compute_through(
            context,
            node,
            functools.partial(_leg_mean_operand, operand.leg_mean, frame, side, bundle),
        )
    if operand.leg_sum is not None:
        return compute_through(
            context,
            node,
            functools.partial(_leg_sum_operand, operand.leg_sum, frame, side, bundle),
        )
    if operand.leg_top_mean is not None:
        return compute_through(
            context,
            node,
            functools.partial(_leg_top_mean_operand, operand.leg_top_mean, frame, side, bundle),
        )
    if operand.anchor_follow is not None:
        return compute_through(
            context,
            node,
            functools.partial(_anchor_follow_operand, operand.anchor_follow, side, bundle),
        )
    if operand.leg_bars is not None:
        return compute_through(
            context,
            node,
            functools.partial(_leg_bars_operand, operand.leg_bars, side, bundle),
        )
    if operand.forming_candle is not None:
        return compute_through(
            context,
            node,
            functools.partial(
                _forming_candle_operand,
                operand.forming_candle,
                frame,
                context,
                identity,
                side,
                bundle,
            ),
        )
    if operand.completed_candle is not None:
        return compute_through(
            context,
            node,
            functools.partial(
                _completed_candle_operand,
                operand.completed_candle,
                frame,
                context,
                identity,
                side,
                bundle,
            ),
        )
    if operand.impulse_atr is not None:
        return compute_through(
            context,
            node,
            functools.partial(
                _impulse_atr_operand, operand.impulse_atr, frame, context, identity, side, bundle
            ),
        )
    if operand.leg_efficiency is not None:
        return compute_through(
            context,
            node,
            functools.partial(_leg_efficiency_operand, operand.leg_efficiency, frame, side, bundle),
        )
    if operand.leg_speed is not None:
        return compute_through(
            context,
            node,
            functools.partial(_leg_speed_operand, operand.leg_speed, frame, side, bundle),
        )
    if operand.pullback_depth is not None:
        return compute_through(
            context,
            node,
            functools.partial(_pullback_depth_operand, operand.pullback_depth, frame, side, bundle),
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


def _candle_operand(
    candle: Candle,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "candle operand has no evaluated episode", episode_ref=candle.episode
        )
    base = frame.market.base_timeframe
    base_ms = timeframe_duration_ms(base)
    timeframe_ms = timeframe_duration_ms(candle.timeframe)
    if timeframe_ms < base_ms or timeframe_ms % base_ms or 86_400_000 % timeframe_ms:
        raise InvalidRequestError(
            "candle timeframe must be a multiple of the base timeframe that divides a day",
            timeframe=candle.timeframe,
            base_timeframe=base,
        )
    atr = None if candle.atr is None else _feature_array(candle.atr, frame, context, identity)
    market = frame_market_arrays(frame)
    return candle_values(
        episodes.side(candle.episode, side),
        time_ms=np.asarray(frame.time_ms, dtype=np.int64),
        open_=market.array("open"),
        high=market.array("high"),
        low=market.array("low"),
        close=market.array("close"),
        timeframe_ms=timeframe_ms,
        base_ms=base_ms,
        leg=candle.leg,
        direction=candle.direction,
        side=side,
        atr=atr,
        atr_period=None if candle.atr is None else int(candle.atr.parameters["period"]),
    )


def _leg_mean_operand(
    leg_mean: LegMean,
    frame: FeatureFrameLike,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "leg_mean operand has no evaluated episode", episode_ref=leg_mean.episode
        )
    arrays = frame_market_arrays(frame)
    if leg_mean.field in FORCE_FIELDS:
        series = force_series(arrays.array("close"), arrays.array("volume"), leg_mean.field, side)
    else:
        series = arrays.array(leg_mean.field)
    return leg_mean_values(episodes.side(leg_mean.episode, side), series, leg_mean.leg)


def _leg_sum_operand(
    leg_sum: LegSum,
    frame: FeatureFrameLike,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "leg_sum operand has no evaluated episode", episode_ref=leg_sum.episode
        )
    arrays = frame_market_arrays(frame)
    if leg_sum.field == OWN_COLOR_VOLUME:
        series = own_color_volume_series(
            arrays.array("open"), arrays.array("close"), arrays.array("volume"), side, leg_sum.leg
        )
    else:
        series = arrays.array(leg_sum.field)
    return leg_sum_values(episodes.side(leg_sum.episode, side), series, leg_sum.leg)


def _leg_top_mean_operand(
    leg_top_mean: LegTopMean,
    frame: FeatureFrameLike,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "leg_top_mean operand has no evaluated episode", episode_ref=leg_top_mean.episode
        )
    series = frame_market_arrays(frame).array(leg_top_mean.field)
    return leg_top_mean_values(
        episodes.side(leg_top_mean.episode, side), series, leg_top_mean.leg, leg_top_mean.share
    )


def _anchor_follow_operand(
    anchor_follow: AnchorFollow, side: str, bundle: ContextBundle | None
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "anchor_follow operand has no evaluated episode", episode_ref=anchor_follow.episode
        )
    return anchor_follow_values(episodes.side(anchor_follow.episode, side))


def _pullback_depth_operand(
    pullback_depth: PullbackDepth,
    frame: FeatureFrameLike,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "pullback_depth operand has no evaluated episode", episode_ref=pullback_depth.episode
        )
    market = frame_market_arrays(frame)
    return pullback_depth_values(
        episodes.side(pullback_depth.episode, side),
        market.array("low"),
        market.array("high"),
        pullback_depth.touch,
    )


def _leg_efficiency_operand(
    leg_efficiency: LegEfficiency,
    frame: FeatureFrameLike,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "leg_efficiency operand has no evaluated episode", episode_ref=leg_efficiency.episode
        )
    close = frame_market_arrays(frame).array("close")
    return leg_efficiency_values(
        episodes.side(leg_efficiency.episode, side), close, leg_efficiency.leg
    )


def _leg_speed_operand(
    leg_speed: LegSpeed,
    frame: FeatureFrameLike,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "leg_speed operand has no evaluated episode", episode_ref=leg_speed.episode
        )
    close = frame_market_arrays(frame).array("close")
    return leg_speed_values(episodes.side(leg_speed.episode, side), close, leg_speed.leg)


def _leg_bars_operand(leg_bars: LegBars, side: str, bundle: ContextBundle | None) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "leg_bars operand has no evaluated episode", episode_ref=leg_bars.episode
        )
    return leg_bars_values(episodes.side(leg_bars.episode, side), leg_bars.leg)


def _forming_candle_operand(
    forming_candle: FormingCandle,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "forming_candle operand has no evaluated episode", episode_ref=forming_candle.episode
        )
    base = frame.market.base_timeframe
    base_ms = timeframe_duration_ms(base)
    timeframe_ms = timeframe_duration_ms(forming_candle.timeframe)
    if timeframe_ms <= base_ms or timeframe_ms % base_ms or 86_400_000 % timeframe_ms:
        raise InvalidRequestError(
            "forming candle timeframe must be a longer multiple of the base timeframe "
            "that divides a day",
            timeframe=forming_candle.timeframe,
            base_timeframe=base,
        )
    market = frame_market_arrays(frame)
    return forming_candle_values(
        episodes.side(forming_candle.episode, side),
        time_ms=np.asarray(frame.time_ms, dtype=np.int64),
        open_=market.array("open"),
        close=market.array("close"),
        timeframe_ms=timeframe_ms,
        atr=_feature_array(forming_candle.atr, frame, context, identity),
    )


def _completed_candle_operand(
    completed_candle: CompletedCandle,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "completed_candle operand has no evaluated episode",
            episode_ref=completed_candle.episode,
        )
    base = frame.market.base_timeframe
    base_ms = timeframe_duration_ms(base)
    timeframe_ms = timeframe_duration_ms(completed_candle.timeframe)
    if timeframe_ms <= base_ms or timeframe_ms % base_ms or (
        86_400_000 % timeframe_ms and timeframe_ms % 604_800_000
    ):
        raise InvalidRequestError(
            "completed candle timeframe must be a longer multiple of the base timeframe "
            "that divides a day, or whole weeks",
            timeframe=completed_candle.timeframe,
            base_timeframe=base,
        )
    market = frame_market_arrays(frame)
    return completed_candle_values(
        episodes.side(completed_candle.episode, side),
        time_ms=np.asarray(frame.time_ms, dtype=np.int64),
        open_=market.array("open"),
        high=market.array("high"),
        low=market.array("low"),
        close=market.array("close"),
        timeframe_ms=timeframe_ms,
        field=completed_candle.field,
        atr=_feature_array(completed_candle.atr, frame, context, identity),
    )


def _impulse_atr_operand(
    impulse_atr: ImpulseAtr,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    side: str,
    bundle: ContextBundle | None,
) -> np.ndarray:
    episodes = bundle.episodes if bundle is not None else None
    if episodes is None:
        raise InvalidRequestError(
            "impulse_atr operand has no evaluated episode", episode_ref=impulse_atr.episode
        )
    atr = _feature_array(impulse_atr.atr, frame, context, identity)
    return impulse_atr_values(episodes.side(impulse_atr.episode, side), atr)


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
        "touch": _take_rows(episode.touches["touch_bar"], rows, valid),
        "current": np.arange(size, dtype=np.float64),
    }
    if segment.touch == "previous":
        # Same episode only: the first touch has no previous one.
        has_previous = valid & (count >= 2)
        earlier = np.where(has_previous, rows - 1, 0)
        strict = False
        begin = _take_rows(episode.touches[_TOUCH_COLUMNS[segment.start]], earlier, has_previous)
        if segment.end == "next_origin":
            # The previous pullback runs to the true low that starts the
            # current wave: the origin of the current touch (known at t).
            end = _take_rows(episode.touches["origin_bar"], rows, has_previous)
            strict = True
        else:
            end = _take_rows(episode.touches[_TOUCH_COLUMNS[segment.end]], earlier, has_previous)
    else:
        begin, end = points[segment.start], points[segment.end]
        strict = False
    with np.errstate(invalid="ignore"):
        ok = valid & np.isfinite(begin) & np.isfinite(end)
        ok &= (begin < end) if strict else (begin <= end)
        ok &= end <= np.arange(size)  # nothing after the evaluated bar is read
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
        level = window_extreme(clean, low, high, segment.aggregate == "max")
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
        result[rows] = window_extreme(changes, low, high, segment.aggregate == "max")
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
    if not (isinstance(condition, Range) and _has_value(condition.operand)):
        return None
    value = _values(condition.operand, frame, context, identity, side, bundle, "operand")
    assert isinstance(value, np.ndarray)
    return value


def range_operand_values(
    predicate: AnyPredicate,
    frame: FeatureFrameLike,
    side: str,
    *,
    context: EvaluationContext | None = None,
    identity: PredicateIdentity | None = None,
    bundle: ContextBundle | None = None,
) -> np.ndarray:
    """The operand value of a `range`, on the base timeline for `side`, NaN
    where missing, for any operand a `range` accepts (OpenSpec
    `weighted-vote-setup-v1`, design D2). Consumes exactly the nodes the
    range's own evaluation consumes for its operand."""

    if side not in _SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    if not isinstance(predicate, Predicate):
        raise InvalidRequestError("operand value requires a range predicate")
    condition = predicate.for_side(side)
    if not isinstance(condition, Range):
        raise InvalidRequestError("operand value requires a range predicate")
    value = _values(condition.operand, frame, context, identity, side, bundle, "operand")
    length = len(frame.time_ms)
    array = np.broadcast_to(np.asarray(value, dtype=np.float64), (length,))
    return np.where(np.isfinite(array), array, np.nan)


def _has_value(operand: Operand) -> bool:
    return (
        operand.segment is not None
        or operand.ratio is not None
        or operand.candle is not None
        or operand.leg_mean is not None
        or operand.leg_sum is not None
        or operand.leg_top_mean is not None
        or operand.anchor_follow is not None
        or operand.pullback_depth is not None
        or operand.leg_speed is not None
        or operand.impulse_atr is not None
        or operand.leg_bars is not None
        or operand.forming_candle is not None
        or operand.leg_efficiency is not None
        or operand.completed_candle is not None
    )


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
    if operand.candle is not None:
        return ("candle",)
    if operand.leg_mean is not None:
        return ("leg_mean",)
    if operand.leg_sum is not None:
        return ("leg_sum",)
    if operand.leg_top_mean is not None:
        return ("leg_top_mean",)
    if operand.anchor_follow is not None:
        return ("anchor_follow",)
    if operand.pullback_depth is not None:
        return ("pullback_depth",)
    if operand.leg_speed is not None:
        return ("leg_speed",)
    if operand.leg_efficiency is not None:
        return ("leg_efficiency",)
    if operand.impulse_atr is not None:
        return ("impulse_atr",)
    if operand.leg_bars is not None:
        return ("leg_bars",)
    if operand.forming_candle is not None:
        return ("forming_candle",)
    if operand.completed_candle is not None:
        return ("completed_candle",)
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
        if isinstance(condition, Range) and _has_value(condition.operand)
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
    if operand.candle is not None:
        candle = operand.candle
        episode = (contexts or {}).get(episode_identity_key(candle.episode, side))
        if episode is None:
            raise InvalidRequestError("candle episode is not declared", episode_ref=candle.episode)
        upstream = {"episode": episode}
        consumed = []
        if candle.atr is not None:
            column = _column_identity(candle.atr, feature_ids, column_ids)
            upstream[CANDLE_ATR_FIELD] = column
            consumed.append(column)
        node = node_spec(
            "predicate.candle",
            version=PREDICATE_NODE_VERSION,
            params={
                "leg": candle.leg,
                "timeframe": candle.timeframe,
                "direction": candle.direction,
            },
            upstream=upstream,
            side=side,
        )
        operand_ids[path] = node
        return node, [node, *consumed]
    if operand.leg_mean is not None:
        leg_mean = operand.leg_mean
        episode = (contexts or {}).get(episode_identity_key(leg_mean.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "leg_mean episode is not declared", episode_ref=leg_mean.episode
            )
        node = node_spec(
            "predicate.leg_mean",
            version=PREDICATE_NODE_VERSION,
            params={"leg": leg_mean.leg, "field": leg_mean.field},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.leg_sum is not None:
        leg_sum = operand.leg_sum
        episode = (contexts or {}).get(episode_identity_key(leg_sum.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "leg_sum episode is not declared", episode_ref=leg_sum.episode
            )
        node = node_spec(
            "predicate.leg_sum",
            version=PREDICATE_NODE_VERSION,
            params={"leg": leg_sum.leg, "field": leg_sum.field},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.leg_top_mean is not None:
        leg_top_mean = operand.leg_top_mean
        episode = (contexts or {}).get(episode_identity_key(leg_top_mean.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "leg_top_mean episode is not declared", episode_ref=leg_top_mean.episode
            )
        node = node_spec(
            "predicate.leg_top_mean",
            version=PREDICATE_NODE_VERSION,
            params={
                "leg": leg_top_mean.leg,
                "field": leg_top_mean.field,
                "share": leg_top_mean.share,
            },
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.anchor_follow is not None:
        anchor_follow = operand.anchor_follow
        episode = (contexts or {}).get(episode_identity_key(anchor_follow.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "anchor_follow episode is not declared", episode_ref=anchor_follow.episode
            )
        node = node_spec(
            "predicate.anchor_follow",
            version=PREDICATE_NODE_VERSION,
            params={},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.leg_bars is not None:
        leg_bars = operand.leg_bars
        episode = (contexts or {}).get(episode_identity_key(leg_bars.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "leg_bars episode is not declared", episode_ref=leg_bars.episode
            )
        node = node_spec(
            "predicate.leg_bars",
            version=PREDICATE_NODE_VERSION,
            params={"leg": leg_bars.leg},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.forming_candle is not None:
        forming_candle = operand.forming_candle
        episode = (contexts or {}).get(episode_identity_key(forming_candle.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "forming_candle episode is not declared", episode_ref=forming_candle.episode
            )
        column = _column_identity(forming_candle.atr, feature_ids, column_ids)
        node = node_spec(
            "predicate.forming_candle",
            version=PREDICATE_NODE_VERSION,
            params={"timeframe": forming_candle.timeframe},
            upstream={"episode": episode, FORMING_CANDLE_ATR_FIELD: column},
            side=side,
        )
        operand_ids[path] = node
        return node, [node, column]
    if operand.completed_candle is not None:
        completed_candle = operand.completed_candle
        episode = (contexts or {}).get(episode_identity_key(completed_candle.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "completed_candle episode is not declared", episode_ref=completed_candle.episode
            )
        column = _column_identity(completed_candle.atr, feature_ids, column_ids)
        node = node_spec(
            "predicate.completed_candle",
            version=PREDICATE_NODE_VERSION,
            params={"timeframe": completed_candle.timeframe, "field": completed_candle.field},
            upstream={"episode": episode, COMPLETED_CANDLE_ATR_FIELD: column},
            side=side,
        )
        operand_ids[path] = node
        return node, [node, column]
    if operand.impulse_atr is not None:
        impulse_atr = operand.impulse_atr
        episode = (contexts or {}).get(episode_identity_key(impulse_atr.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "impulse_atr episode is not declared", episode_ref=impulse_atr.episode
            )
        column = _column_identity(impulse_atr.atr, feature_ids, column_ids)
        node = node_spec(
            "predicate.impulse_atr",
            version=PREDICATE_NODE_VERSION,
            params={},
            upstream={"episode": episode, IMPULSE_ATR_FIELD: column},
            side=side,
        )
        operand_ids[path] = node
        return node, [node, column]
    if operand.leg_efficiency is not None:
        leg_efficiency = operand.leg_efficiency
        episode = (contexts or {}).get(episode_identity_key(leg_efficiency.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "leg_efficiency episode is not declared", episode_ref=leg_efficiency.episode
            )
        node = node_spec(
            "predicate.leg_efficiency",
            version=PREDICATE_NODE_VERSION,
            params={"leg": leg_efficiency.leg},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.leg_speed is not None:
        leg_speed = operand.leg_speed
        episode = (contexts or {}).get(episode_identity_key(leg_speed.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "leg_speed episode is not declared", episode_ref=leg_speed.episode
            )
        node = node_spec(
            "predicate.leg_speed",
            version=PREDICATE_NODE_VERSION,
            params={"leg": leg_speed.leg},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
    if operand.pullback_depth is not None:
        pullback_depth = operand.pullback_depth
        episode = (contexts or {}).get(episode_identity_key(pullback_depth.episode, side))
        if episode is None:
            raise InvalidRequestError(
                "pullback_depth episode is not declared", episode_ref=pullback_depth.episode
            )
        node = node_spec(
            "predicate.pullback_depth",
            version=PREDICATE_NODE_VERSION,
            params={} if pullback_depth.touch == "current" else {"touch": pullback_depth.touch},
            upstream={"episode": episode},
            side=side,
        )
        operand_ids[path] = node
        return node, [node]
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
