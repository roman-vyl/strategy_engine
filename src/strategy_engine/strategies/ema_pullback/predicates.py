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
class Operand:
    """Exactly one of a canonical feature request, a base-bar price field or
    a numeric constant."""

    feature: PlannedFeature | None = None
    price: str | None = None
    const: float | None = None


@dataclass(frozen=True, slots=True)
class Compare:
    left: Operand
    op: str
    right: Operand


@dataclass(frozen=True, slots=True)
class Range:
    operand: Operand
    min: float
    max: float


Condition = Compare | Range


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
                if operand.feature is not None:
                    out.append(operand.feature)
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


def _operand(raw: object, path: str) -> Operand:
    payload = _mapping(raw, path)
    if len(payload) != 1:
        raise InvalidRequestError(f"{path} must carry exactly one of feature, price or const")
    ((key, value),) = payload.items()
    if key == "feature":
        return Operand(feature=_feature(value, f"{path}.feature"))
    if key == "price":
        if value not in _PRICE_FIELDS:
            raise InvalidRequestError(f"{path}.price must be open, high, low or close")
        return Operand(price=str(value))
    if key == "const":
        return Operand(const=_number(value, f"{path}.const"))
    raise InvalidRequestError(f"{path} must carry exactly one of feature, price or const")


def _compare(payload: Mapping[str, Any], path: str) -> Compare:
    op = payload.get("op")
    if op not in _COMPARE_OPS:
        raise InvalidRequestError(f"{path}.op must be one of >, >=, <, <=", op=op)
    left = _operand(payload.get("left"), f"{path}.left")
    right = _operand(payload.get("right"), f"{path}.right")
    if left.const is not None and right.const is not None:
        raise InvalidRequestError(f"{path} must compare at least one non-constant operand")
    return Compare(left, str(op), right)


def _range(payload: Mapping[str, Any], path: str) -> Range:
    operand = _operand(payload.get("operand"), f"{path}.operand")
    if operand.const is not None:
        raise InvalidRequestError(f"{path}.operand must be a feature or a price")
    low = _number(payload.get("min"), f"{path}.min")
    high = _number(payload.get("max"), f"{path}.max")
    if low > high:
        raise InvalidRequestError(f"{path}.min must not exceed max")
    return Range(operand, low, high)


_CLASS_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    # class -> (condition fields, fields a `short` override may replace)
    "compare": ({"left", "op", "right"}, {"left", "op", "right"}),
    "range": ({"operand", "min", "max"}, {"min", "max"}),
}


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
    payload: Mapping[str, Any], path: str, context_refs: Collection[str] | None
) -> TemporalPredicate:
    _only_fields(payload, {"kind", "mode", "bars", "of"}, path)
    mode = payload.get("mode")
    if mode not in _TEMPORAL_MODES:
        raise InvalidRequestError(f"{path}.mode must be held_for or within", mode=mode)
    bars = payload.get("bars")
    if isinstance(bars, bool) or not isinstance(bars, int) or bars < 1:
        raise InvalidRequestError(f"{path}.bars must be a positive integer", bars=bars)
    inner = parse_predicate(payload.get("of"), f"{path}.of", context_refs=context_refs)
    if isinstance(inner, TemporalPredicate):
        raise InvalidRequestError(f"{path}.of must not be temporal")
    return TemporalPredicate(str(mode), bars, inner)


def parse_predicate(
    raw: object, path: str, *, context_refs: Collection[str] | None = None
) -> AnyPredicate:
    """Parse and validate one predicate object. Feature operands are
    validated by the canonical feature-kind contract, never here.
    `context_refs`: the spec's declared contexts (None skips that check;
    evaluation then fails closed on an unknown context)."""

    payload = _mapping(raw, path)
    kind = payload.get("kind")
    if kind == "state":
        return _state(payload, path, context_refs)
    if kind == "temporal":
        return _temporal(payload, path, context_refs)
    if kind not in _CLASS_FIELDS:
        raise InvalidRequestError(
            f"{path}.kind must be compare, range, state or temporal", kind=kind
        )
    fields, overridable = _CLASS_FIELDS[kind]
    _only_fields(payload, {"kind", "short", *fields}, path)
    parse = _compare if kind == "compare" else _range
    long = parse(payload, path)
    short: Condition | None = None
    if payload.get("short") is not None:
        override = _mapping(payload.get("short"), f"{path}.short")
        if not override:
            raise InvalidRequestError(f"{path}.short must not be empty")
        _only_fields(override, overridable, f"{path}.short")
        short = parse({**payload, **override}, f"{path}.short")
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


def _values(
    operand: Operand,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    column_ids: Mapping[str, NodeSpec] | None,
) -> np.ndarray | float:
    if operand.const is not None:
        return operand.const
    if operand.price is not None:
        return frame_market_arrays(frame).array(operand.price)
    assert operand.feature is not None
    label = operand.feature.output_id
    return compute_through(
        context,
        column_ids.get(label) if column_ids is not None else None,
        functools.partial(_column_array, frame, label),
    )


def _finite(values: np.ndarray | float) -> np.ndarray | bool:
    return np.isfinite(values)


def _evaluate_condition(
    condition: Condition,
    frame: FeatureFrameLike,
    context: EvaluationContext | None,
    column_ids: Mapping[str, NodeSpec] | None,
) -> np.ndarray:
    length = len(frame.time_ms)
    if isinstance(condition, Compare):
        left = _values(condition.left, frame, context, column_ids)
        right = _values(condition.right, frame, context, column_ids)
        result = _finite(left) & _finite(right) & _COMPARE_OPS[condition.op](left, right)
    else:
        value = _values(condition.operand, frame, context, column_ids)
        result = _finite(value) & (value >= condition.min) & (value <= condition.max)
    mask = np.broadcast_to(np.asarray(result, dtype=bool), (length,)).copy()
    mask.flags.writeable = False
    return mask


def _state_mask(
    predicate: StatePredicate, frame: FeatureFrameLike, side: str, bundle: ContextBundle | None
) -> np.ndarray:
    from strategy_engine.strategies.ema_pullback.context_consumption import resolve_htf_regime

    output = next(
        (item for item in (bundle.outputs if bundle else ()) if item.context_ref
         == predicate.context_ref),
        None,
    )
    if output is None:
        raise InvalidRequestError(
            "state predicate context is not evaluated", context_ref=predicate.context_ref
        )
    mask = np.zeros(len(frame.time_ms), dtype=bool)
    for raw_state, raw_mask in (("up", output.up), ("down", output.down),
                                ("neutral", output.neutral)):
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
        column_ids = identity.column_ids if identity is not None else None
        return _evaluate_condition(predicate.for_side(side), frame, context, column_ids)
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


def column_node(feature: NodeSpec) -> NodeSpec:
    return node_spec(
        "predicate.column", version=PREDICATE_NODE_VERSION, upstream={"feature": feature}
    )


def _operand_param(operand: Operand) -> tuple[object, ...]:
    if operand.const is not None:
        return ("const", operand.const)
    if operand.price is not None:
        return ("price", operand.price)
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
    roles = ("left", "right") if isinstance(condition, Compare) else ("operand",)
    for role, operand in zip(roles, _operands(condition), strict=True):
        if operand.feature is None:
            continue
        label = operand.feature.output_id
        try:
            feature = feature_ids[label]
        except KeyError as exc:
            raise InvalidRequestError("missing planned feature series", output_id=label) from exc
        column = column_node(feature)
        upstream[role] = column
        columns.append(column)
        column_ids[label] = column
    if isinstance(condition, Compare):
        kind = "predicate.compare"
        params: dict[str, object] = {
            "op": condition.op,
            "left": _operand_param(condition.left),
            "right": _operand_param(condition.right),
        }
    else:
        kind = "predicate.range"
        params = {
            "operand": _operand_param(condition.operand),
            "min": condition.min,
            "max": condition.max,
        }
    local = node_spec(
        kind,
        version=PREDICATE_NODE_VERSION,
        params=params,
        upstream=upstream,
        side=side if predicate.short is not None else None,
    )
    return PredicateIdentity(local, tuple(columns), column_ids)
