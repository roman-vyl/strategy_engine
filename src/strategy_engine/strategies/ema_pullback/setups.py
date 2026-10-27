"""BBB-compatible ema_pullback setup components and composition."""

from __future__ import annotations

import functools
import math
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from typing import Any

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.evaluation_context import EvaluationContext, compute_through
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.ema_pullback.composite_spec import (
    COMPOSITE_SETUP,
    CompositeSpec,
    child_instance_key,
    child_setup_item,
    parse_composite_setup,
)
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
    GateIdentity,
)
from strategy_engine.strategies.ema_pullback.contexts import ContextBundle
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    SideDirectionBlockerIdentity,
    SideDirectionBlockers,
    and_masks_node,
    and_pair,
    gate_node_for,
    gated_mask_node,
    pairwise_and_node,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
)
from strategy_engine.strategies.ema_pullback.predicates import (
    PredicateIdentity,
    evaluate_predicate,
    parse_predicate,
    predicate_value,
    range_operand_values,
    resolve_predicate,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    SETUP_SUPPORTED,
    WIDTH_BAND_SETUP,
    parse_width_band_params,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_setup_identity as _setup_identity,
)
from strategy_engine.strategies.ema_pullback.weighted_vote_spec import (
    WEIGHT_SCALE,
    WEIGHTED_VOTE_SETUP,
    Exponent,
    VoteInput,
    WeightedVoteSpec,
    parse_weighted_vote_setup,
    scaled_to_text,
)

_VALID_SIDES = frozenset({"long", "short"})


@dataclass(frozen=True, slots=True)
class SetupMask:
    component_id: str
    instance_id: str
    side: str
    local_setup_allowed: tuple[bool, ...]
    context_gate_allowed: tuple[bool, ...] | None
    final_setup_allowed: tuple[bool, ...]
    trace: dict[str, tuple[object, ...]]

    def to_wire(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "instance_id": self.instance_id,
            "side": self.side,
            "local_setup_allowed": list(self.local_setup_allowed),
            "context_gate_allowed": (
                list(self.context_gate_allowed) if self.context_gate_allowed is not None else None
            ),
            "final_setup_allowed": list(self.final_setup_allowed),
            "trace": {key: list(values) for key, values in self.trace.items()},
        }


@dataclass(frozen=True, slots=True)
class SideSetupEvaluation:
    side: str
    setups: tuple[SetupMask, ...]
    setups_ok: tuple[bool, ...]
    pre_trigger_allowed: tuple[bool, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "side": self.side,
            "setups": [item.to_wire() for item in self.setups],
            "setups_ok": list(self.setups_ok),
            "pre_trigger_allowed": list(self.pre_trigger_allowed),
        }


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _sequence(value: object, path: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(value)


def _float_series(frame: FeatureFrameLike, output_id: str) -> tuple[float, ...]:
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc
    return tuple(float("nan") if value is None else float(value) for value in values)


def _market_values(frame: FeatureFrameLike, field: str) -> tuple[float, ...]:
    if len(frame.market_bars) != len(frame.time_ms):
        raise InvalidRequestError("market bars unavailable for setup evaluation")
    return frame_market_arrays(frame).values(field)


def _gate_for(
    records: tuple[ContextConsumptionRecord, ...],
    *,
    instance_id: str,
    side: str,
) -> tuple[bool, ...] | None:
    for record in records:
        if record.role == "setup" and record.instance_id == instance_id and record.side == side:
            return record.allowed
    return None


def _apply_gate(local: tuple[bool, ...], gate: tuple[bool, ...] | None) -> tuple[bool, ...]:
    if gate is None:
        return local
    if len(gate) != len(local):
        raise InvalidRequestError("context gate length does not match setup mask")
    return tuple(left and right for left, right in zip(local, gate, strict=True))


def _untouched_anchor_params(params: Mapping[str, Any]) -> tuple[int, int]:
    """Effective `(lookback, active_bars)`, post-defaults (shared by compute
    and resolve)."""

    lookback = int(params.get("lookback", 50))
    active_bars = int(params.get("active_bars", 3))
    if lookback <= 0 or active_bars <= 0:
        raise InvalidRequestError("untouched anchor setup periods must be positive")
    return lookback, active_bars


def _untouched_anchor(
    frame: FeatureFrameLike,
    anchor_id: str,
    params: Mapping[str, Any],
    side: str,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    lookback, active_bars = _untouched_anchor_params(params)
    anchor = _float_series(frame, anchor_id)
    close = _market_values(frame, "close")
    low = _market_values(frame, "low")
    high = _market_values(frame, "high")
    touch = tuple(
        low_value <= anchor_value if side == "long" else high_value >= anchor_value
        for low_value, high_value, anchor_value in zip(low, high, anchor, strict=True)
    )
    side_ok = tuple(
        close_value > anchor_value if side == "long" else close_value < anchor_value
        for close_value, anchor_value in zip(close, anchor, strict=True)
    )
    prior_touch = (False,) + touch[:-1]
    # Vectorized, positional replacement for the per-bar Python loop
    # (design.md Decision 1, ema-pullback-setup-vectorization): shift(1)
    # excludes the current bar from the window (matching
    # touch[index-lookback:index]); min_periods=lookback reproduces "full
    # lookback required"; positions before `lookback` are hard-forced to
    # False, matching the original's explicit `continue` branch exactly.
    touch_arr = np.asarray(touch, dtype=bool)
    n = len(touch_arr)
    shifted = pd.Series(touch_arr).shift(1, fill_value=False)
    seen = shifted.rolling(lookback, min_periods=lookback).max()
    untouched_prior_arr = np.where(
        np.arange(n) < lookback, False, (~seen.fillna(1).astype(bool)).to_numpy()
    )
    untouched_prior = untouched_prior_arr.tolist()
    armed_pre = tuple(
        ok and untouched and not touched
        for ok, untouched, touched in zip(side_ok, untouched_prior, touch, strict=True)
    )
    first_touch = tuple(
        touched and untouched for touched, untouched in zip(touch, untouched_prior, strict=True)
    )
    # Vectorized, positional replacement for the per-bar Python loop
    # (design.md Decision 2): min_periods=1 reproduces the original's
    # start-of-series window clipping (max(0, index-active_bars+1)) exactly,
    # same technique as the already-shipped _rsi_blocker.
    touch_active_arr = (
        pd.Series(np.asarray(first_touch, dtype=bool))
        .rolling(active_bars, min_periods=1)
        .max()
        .to_numpy()
        .astype(bool)
    )
    touch_active = tuple(touch_active_arr.tolist())
    setup = tuple(armed or active for armed, active in zip(armed_pre, touch_active, strict=True))
    return setup, {
        "touch": touch,
        "side_ok": side_ok,
        "prior_touch": prior_touch,
        "untouched_prior": tuple(untouched_prior),
        "armed_pre": armed_pre,
        "first_touch": first_touch,
        "touch_active": touch_active,
    }


def _ema_bounce_counter_params(params: Mapping[str, Any]) -> tuple[int, str, int, int, int]:
    """Effective `(max_bounces, raw_touch_mode, touch_lookback_bars,
    trend_start_confirmation_bars, trend_break_confirmation_bars)`,
    post-defaults (shared by compute and resolve)."""

    max_bounces = int(params.get("max_bounces", 3))
    raw_touch_mode = str(params.get("raw_touch_mode", "range_cross"))
    touch_lookback = int(params.get("touch_lookback_bars", 10))
    start_confirm = int(params.get("trend_start_confirmation_bars", 1))
    break_confirm = int(params.get("trend_break_confirmation_bars", 1))
    if max_bounces <= 0 or touch_lookback <= 0 or start_confirm <= 0 or break_confirm <= 0:
        raise InvalidRequestError("ema bounce counter parameters must be positive")
    if raw_touch_mode != "range_cross":
        raise InvalidRequestError("raw_touch_mode must be range_cross")
    return max_bounces, raw_touch_mode, touch_lookback, start_confirm, break_confirm


def _ema_bounce_counter(
    frame: FeatureFrameLike,
    columns: Mapping[str, str],
    params: Mapping[str, Any],
    side: str,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    max_bounces, _raw_touch_mode, touch_lookback, start_confirm, break_confirm = (
        _ema_bounce_counter_params(params)
    )
    fast = _float_series(frame, columns["fast"])
    anchor = _float_series(frame, columns["anchor"])
    slow = _float_series(frame, columns["slow"])
    close = _market_values(frame, "close")
    low = _market_values(frame, "low")
    high = _market_values(frame, "high")
    if side == "long":
        raw_trend = tuple(f > a and a > s for f, a, s in zip(fast, anchor, slow, strict=True))
        armed_series = tuple(c > a for c, a in zip(close, anchor, strict=True))
    else:
        raw_trend = tuple(f < a and a < s for f, a, s in zip(fast, anchor, slow, strict=True))
        armed_series = tuple(c < a for c, a in zip(close, anchor, strict=True))
    raw_touch_series = tuple(lo <= a <= hi for lo, a, hi in zip(low, anchor, high, strict=True))

    values: dict[str, list[object]] = {
        "trend_active": [],
        "trend_episode_id": [],
        "armed": [],
        "raw_touch": [],
        "pending_bounce": [],
        "in_touch_lookback": [],
        "touch_lookback_left": [],
        "completed_bounce_count": [],
        "effective_bounce_number": [],
        "setup_allowed": [],
        "price_side_of_anchor": [],
        "trend_start_event": [],
        "trend_break_event": [],
        "pending_bounce_start": [],
        "pending_bounce_end": [],
    }
    trend_active = False
    trend_episode_id = 0
    raw_trend_run = 0
    raw_break_run = 0
    completed_count = 0
    pending = False
    pending_end_idx = -1
    for index in range(len(frame.time_ms)):
        if pending and index > pending_end_idx:
            completed_count += 1
            pending = False
            pending_end_idx = -1
        trend_start_event = False
        trend_break_event = False
        if trend_active:
            if raw_trend[index]:
                raw_break_run = 0
            else:
                raw_break_run += 1
                if raw_break_run >= break_confirm:
                    trend_active = False
                    trend_break_event = True
                    completed_count = 0
                    pending = False
                    pending_end_idx = -1
                    raw_trend_run = 0
                    raw_break_run = 0
        else:
            if raw_trend[index]:
                raw_trend_run += 1
                if raw_trend_run >= start_confirm:
                    trend_active = True
                    trend_start_event = True
                    trend_episode_id += 1
                    completed_count = 0
                    pending = False
                    pending_end_idx = -1
                    raw_break_run = 0
            else:
                raw_trend_run = 0
        pending_start = False
        if (
            trend_active
            and armed_series[index]
            and raw_touch_series[index]
            and not pending
            and completed_count < max_bounces
        ):
            pending = True
            pending_start = True
            pending_end_idx = index + touch_lookback - 1
        pending_end = pending and index == pending_end_idx
        in_lookback = pending and index <= pending_end_idx
        lookback_left = max(pending_end_idx - index + 1, 0) if in_lookback else 0
        effective = completed_count + 1 if pending else completed_count
        allowed = trend_active and (
            completed_count < max_bounces or (pending and completed_count + 1 <= max_bounces)
        )
        price_side = (
            "above"
            if close[index] > anchor[index]
            else "below"
            if close[index] < anchor[index]
            else "at"
        )
        row = {
            "trend_active": trend_active,
            "trend_episode_id": trend_episode_id if trend_active else 0,
            "armed": armed_series[index],
            "raw_touch": raw_touch_series[index],
            "pending_bounce": pending,
            "in_touch_lookback": in_lookback,
            "touch_lookback_left": lookback_left,
            "completed_bounce_count": completed_count,
            "effective_bounce_number": effective,
            "setup_allowed": allowed,
            "price_side_of_anchor": price_side,
            "trend_start_event": trend_start_event,
            "trend_break_event": trend_break_event,
            "pending_bounce_start": pending_start,
            "pending_bounce_end": pending_end,
        }
        for key, value in row.items():
            values[key].append(value)
    trace = {key: tuple(items) for key, items in values.items()}
    return tuple(bool(item) for item in trace["setup_allowed"]), trace


def _anchor_stack_width_params(params: Mapping[str, Any]) -> tuple[float, float, int]:
    """Effective `(min_current_width_atr, min_recent_width_atr,
    width_lookback_bars)`, post-defaults (shared by compute and resolve)."""

    min_current = float(params.get("min_current_width_atr", 2.0))
    min_recent = float(params.get("min_recent_width_atr", 4.0))
    lookback = int(params.get("width_lookback_bars", 80))
    if min_current <= 0 or min_recent <= 0 or lookback <= 0:
        raise InvalidRequestError("anchor stack width parameters must be positive")
    return min_current, min_recent, lookback


def _anchor_stack_width_prefix(
    fast: tuple[float, ...],
    slow: tuple[float, ...],
    atr: tuple[float, ...],
    lookback: int,
) -> tuple[tuple[float, ...], list[float]]:
    """Side-free, threshold-free prefix of the width setup: per-bar
    `width_atr` and its trailing `recent_max` over `lookback` bars. Depends
    only on (fast, slow, atr, lookback) -- not on the anchor or on either
    width threshold, which only the suffix reads."""

    width_atr = tuple(
        abs(f - s) / a if all(isfinite(v) for v in (f, s, a)) and a > 0 else float("nan")
        for f, s, a in zip(fast, slow, atr, strict=True)
    )
    # Vectorized, positional replacement for the per-bar Python loop
    # (design.md Decision 3, ema-pullback-setup-vectorization): ordinary
    # rolling().max() silently skips NaN, which is NOT the original
    # semantics (all(isfinite(v) for v in window) gates the whole window to
    # NaN if any element is non-finite). roll_all_finite uses a rolling SUM
    # of a 0/1 finiteness indicator compared with .eq(lookback) -- not
    # rolling().min().astype(bool), because an incomplete window
    # (min_periods=lookback) produces NaN from .min(), and NaN casts to True
    # under .astype(bool), which would wrongly pass the gate before a full
    # window exists. .eq(lookback) evaluates a NaN sum to False, so the gate
    # stays explicitly False (recent_max NaN) until a full window exists.
    width_arr = np.asarray(width_atr, dtype=float)
    finite_arr = np.isfinite(width_arr)
    roll_max = pd.Series(width_arr).rolling(lookback, min_periods=lookback).max()
    roll_all_finite = (
        pd.Series(finite_arr.astype(np.int8))
        .rolling(lookback, min_periods=lookback)
        .sum()
        .eq(lookback)
    )
    recent_max: list[float] = roll_max.where(roll_all_finite, other=np.nan).tolist()
    return width_atr, recent_max


def _anchor_stack_width(
    frame: FeatureFrameLike,
    columns: Mapping[str, str],
    params: Mapping[str, Any],
    *,
    context: EvaluationContext | None = None,
    prefix_id: NodeSpec | None = None,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    """The width setup's threshold suffix; its side-free, threshold-free
    prefix is computed through the evaluation context's memo under
    `prefix_id` (batch-computation-reuse 4.6), so candidates that differ only
    in the width thresholds share one prefix computation."""

    min_current, min_recent, lookback = _anchor_stack_width_params(params)
    fast = _float_series(frame, columns["fast"])
    anchor = _float_series(frame, columns["anchor"])
    slow = _float_series(frame, columns["slow"])
    atr = _float_series(frame, columns["atr"])
    width_atr, recent_max = compute_through(
        context,
        prefix_id,
        functools.partial(_anchor_stack_width_prefix, fast, slow, atr, lookback),
    )
    allowed: list[bool] = []
    reasons: list[str] = []
    current_ok: list[bool] = []
    recent_ok: list[bool] = []
    for index, current in enumerate(width_atr):
        recent = recent_max[index]
        not_ready = (
            not all(
                isfinite(value)
                for value in (fast[index], anchor[index], slow[index], atr[index], recent)
            )
            or atr[index] <= 0
        )
        cur = isfinite(current) and current >= min_current
        rec = isfinite(recent) and recent >= min_recent
        current_ok.append(cur)
        recent_ok.append(rec)
        allowed.append(not not_ready and cur and rec)
        if not_ready:
            reasons.append("indicator_not_ready")
        elif not cur:
            reasons.append("current_width_too_narrow")
        elif not rec:
            reasons.append("recent_width_never_expanded")
        else:
            reasons.append("")
    return tuple(allowed), {
        "blocked_reason": tuple(reasons),
        "current_width_atr": tuple(width_atr),
        "recent_max_width_atr": tuple(recent_max),
        "width_lookback_bars": tuple(lookback for _ in width_atr),
        "min_current_width_atr": tuple(min_current for _ in width_atr),
        "min_recent_width_atr": tuple(min_recent for _ in width_atr),
        "current_width_ok": tuple(current_ok),
        "recent_width_ok": tuple(recent_ok),
        "fast_ema": fast,
        "anchor_ema": anchor,
        "slow_ema": slow,
        "atr_value": atr,
    }


def _band_width(
    fast: tuple[float, ...], slow: tuple[float, ...], atr: tuple[float, ...]
) -> tuple[float, ...]:
    """Side-free, threshold-free `width_atr = |fast - slow| / atr` of the band
    setup (NaN where a column is not finite or `atr <= 0`)."""

    fast_arr = np.asarray(fast, dtype=float)
    slow_arr = np.asarray(slow, dtype=float)
    atr_arr = np.asarray(atr, dtype=float)
    ready = np.isfinite(fast_arr) & np.isfinite(slow_arr) & np.isfinite(atr_arr) & (atr_arr > 0)
    safe_atr = np.where(ready, atr_arr, 1.0)
    width = np.where(ready, np.abs(fast_arr - slow_arr) / safe_atr, np.nan)
    return tuple(width.tolist())


def _anchor_stack_width_band(
    frame: FeatureFrameLike,
    columns: Mapping[str, str],
    params: Mapping[str, Any],
    *,
    context: EvaluationContext | None = None,
    width_id: NodeSpec | None = None,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    """Current-bar inclusive band `min <= width_atr <= max` (no upper bound
    when `max_width_atr` is absent); the width is shared through the memo."""

    band = parse_width_band_params(params)
    fast = _float_series(frame, columns["fast"])
    slow = _float_series(frame, columns["slow"])
    atr = _float_series(frame, columns["atr"])
    width = compute_through(context, width_id, functools.partial(_band_width, fast, slow, atr))
    width_arr = np.asarray(width, dtype=float)
    ready = np.isfinite(width_arr)
    with np.errstate(invalid="ignore"):
        below = width_arr < band.min_width_atr
        above = (
            width_arr > band.max_width_atr
            if band.max_width_atr is not None
            else np.zeros(len(width_arr), dtype=bool)
        )
    allowed = ready & ~below & ~above
    reasons = np.where(
        ~ready,
        "indicator_not_ready",
        np.where(below, "width_below_min", np.where(above, "width_above_max", "")),
    )
    size = len(width_arr)
    return tuple(allowed.tolist()), {
        "blocked_reason": tuple(reasons.tolist()),
        "width_atr": width,
        "min_width_atr": tuple(band.min_width_atr for _ in range(size)),
        "max_width_atr": tuple(band.max_width_atr for _ in range(size)),
        "fast_ema": fast,
        "slow_ema": slow,
        "atr_value": atr,
    }


def _combine_setup_masks(
    mask_allowed: tuple[tuple[bool, ...], ...], length: int
) -> tuple[bool, ...]:
    if not mask_allowed:
        return tuple([True] * length)
    stacked = np.array(mask_allowed, dtype=bool)
    reduced = np.logical_and.reduce(stacked, axis=0, initial=True)
    return tuple(reduced.tolist())


def _setup_head(item: Mapping[str, Any], side: str) -> tuple[str, str, Mapping[str, Any]]:
    """Validated `(component_id, instance_id, params)` of one setup item
    (shared by compute and resolve)."""

    component_id, instance_id = _setup_identity(item)
    if component_id not in SETUP_SUPPORTED:
        raise InvalidRequestError("unsupported setup component", component_id=component_id)
    params = _mapping(item.get("params", {}), f"setup[{instance_id}].params")
    if side not in _VALID_SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    return component_id, instance_id, params


def _setup_columns(plan: EmaPullbackFeaturePlan, instance_id: str) -> dict[str, str]:
    columns = plan.setup_columns_by_instance_id.get(instance_id)
    if columns is None:
        raise InvalidRequestError("missing setup feature mapping", instance_id=instance_id)
    return columns


_SetupCompute = functools.partial[tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]]


def _semantic_setup_compute(
    component_id: str,
    instance_id: str,
    params: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    *,
    context: EvaluationContext | None,
    identity: SetupIdentity | None,
) -> _SetupCompute:
    """The local computation of one existing semantic setup, exactly as
    `_setup` dispatched it before `composite_setup` existed (shared by
    top-level setups and composite setup children)."""

    if component_id == "untouched_anchor_setup":
        return functools.partial(
            _untouched_anchor, frame, plan.anchor_columns["anchor"], params, side
        )
    if component_id == "ema_bounce_counter_setup":
        columns = _setup_columns(plan, instance_id)
        return functools.partial(_ema_bounce_counter, frame, columns, params, side)
    columns = _setup_columns(plan, instance_id)
    if component_id == WIDTH_BAND_SETUP:
        return functools.partial(
            _anchor_stack_width_band,
            frame,
            columns,
            params,
            context=context,
            width_id=identity.width_prefix if identity else None,
        )
    return functools.partial(
        _anchor_stack_width,
        frame,
        columns,
        params,
        context=context,
        prefix_id=identity.width_prefix if identity else None,
    )


@dataclass(frozen=True, slots=True)
class CompositeCore:
    """Label-free result of one composite evaluation (the memoized value;
    design D10/D11): child masks in declared child order, path masks and
    at-least counts in declared path order, and the index of the first
    true path per bar (-1 when none)."""

    local: tuple[bool, ...]
    child_masks: tuple[tuple[bool, ...], ...]
    # Operand value per bar (None where missing) of a child that is a range
    # over a segment or ratio, else None (a1-band-filter-v1, design D6).
    child_values: tuple[tuple[float | None, ...] | None, ...]
    path_masks: tuple[tuple[bool, ...], ...]
    at_least_counts: tuple[tuple[int, ...] | None, ...]
    winning_index: tuple[int, ...]


def _composite_core(
    spec: CompositeSpec,
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    *,
    context: EvaluationContext | None,
    children: tuple[SetupIdentity, ...] | None,
    bundle: ContextBundle | None = None,
) -> CompositeCore:
    """Evaluate every child once, then every path, vectorized: a path is
    AND(require) AND (count(of) >= k); the composite is the OR of paths."""

    length = len(frame.time_ms)
    child_masks: list[tuple[bool, ...]] = []
    child_values: list[tuple[float | None, ...] | None] = []
    arrays: dict[str, np.ndarray] = {}
    for index, child in enumerate(spec.children):
        child_identity = children[index] if children is not None else None
        if child.predicate is not None:
            predicate_mask = evaluate_predicate(
                parse_predicate(child.predicate, f"setup[{spec.instance_id}].{child.child_id}"),
                frame,
                side,
                context=context,
                identity=child_identity.predicate if child_identity else None,
                bundle=bundle,
            )
            if len(predicate_mask) != length:
                raise InvalidRequestError(
                    "composite child mask length mismatch", child_id=child.child_id
                )
            child_masks.append(tuple(predicate_mask.tolist()))
            arrays[child.child_id] = predicate_mask
            operand_value = predicate_value(
                parse_predicate(child.predicate, f"setup[{spec.instance_id}].{child.child_id}"),
                frame,
                side,
                context=context,
                identity=child_identity.predicate if child_identity else None,
                bundle=bundle,
            )
            child_values.append(
                None
                if operand_value is None
                else tuple(
                    float(item) if math.isfinite(item) else None
                    for item in operand_value.tolist()
                )
            )
            continue
        item = child_setup_item(spec, child)
        component_id, instance_id, params = _setup_head(item, side)
        compute = _semantic_setup_compute(
            component_id,
            instance_id,
            params,
            frame,
            plan,
            side,
            context=context,
            identity=child_identity,
        )
        mask, _trace = compute_through(
            context, child_identity.local if child_identity else None, compute
        )
        if len(mask) != length:
            raise InvalidRequestError(
                "composite child mask length mismatch", child_id=child.child_id
            )
        child_masks.append(mask)
        child_values.append(None)
        arrays[child.child_id] = np.asarray(mask, dtype=bool)
    path_masks: list[tuple[bool, ...]] = []
    counts: list[tuple[int, ...] | None] = []
    path_arrays: list[np.ndarray] = []
    for composite_path in spec.paths:
        path_mask = np.ones(length, dtype=bool)
        for ref in composite_path.require:
            path_mask &= arrays[ref]
        if composite_path.at_least_k is not None:
            count = np.zeros(length, dtype=np.int64)
            for ref in composite_path.at_least_of:
                count += arrays[ref]
            path_mask &= count >= composite_path.at_least_k
            counts.append(tuple(count.tolist()))
        else:
            counts.append(None)
        path_arrays.append(path_mask)
        path_masks.append(tuple(path_mask.tolist()))
    stacked = np.array(path_arrays, dtype=bool).reshape(len(path_arrays), length)
    local = np.logical_or.reduce(stacked, axis=0, initial=False)
    winning = np.where(local, np.argmax(stacked, axis=0), -1)
    return CompositeCore(
        local=tuple(local.tolist()),
        child_masks=tuple(child_masks),
        child_values=tuple(child_values),
        path_masks=tuple(path_masks),
        at_least_counts=tuple(counts),
        winning_index=tuple(winning.tolist()),
    )


def _composite_trace(spec: CompositeSpec, core: CompositeCore) -> dict[str, tuple[object, ...]]:
    """Attach this item's labels to the label-free core (outside the memo:
    two composites with the same structure but different ids share one
    core yet each get their own labels)."""

    trace: dict[str, tuple[object, ...]] = {}
    for child, mask, values in zip(
        spec.children, core.child_masks, core.child_values, strict=True
    ):
        trace[f"child:{child.child_id}"] = mask
        if values is not None:
            trace[f"child:{child.child_id}:value"] = values
    for composite_path, mask, count in zip(
        spec.paths, core.path_masks, core.at_least_counts, strict=True
    ):
        trace[f"path:{composite_path.path_id}"] = mask
        if count is not None:
            trace[f"path:{composite_path.path_id}:at_least_count"] = count
    labels = np.array([item.path_id for item in spec.paths] + [None], dtype=object)
    trace["winning_path"] = tuple(labels[np.asarray(core.winning_index, dtype=np.int64)].tolist())
    return trace


def _vote_input_crossings(
    vote_input: VoteInput,
    path: str,
    frame: FeatureFrameLike,
    side: str,
    *,
    context: EvaluationContext | None,
    identities: tuple[PredicateIdentity, ...] | None,
    bundle: ContextBundle | None,
    evidence: bool = True,
) -> tuple[tuple[object, ...] | None, tuple[np.ndarray, ...], np.ndarray | None]:
    """`(value trace, crossed mask per step, operand values)` of one vote
    input (design D2, D6): an operand value against its levels, or the number
    of True predicates of `count.of` against integer levels. The value trace
    is None when `evidence` is off; the operand values are None for a count."""

    if vote_input.operand_predicate is not None:
        values = range_operand_values(
            parse_predicate(vote_input.operand_predicate, path),
            frame,
            side,
            context=context,
            identity=identities[0] if identities is not None else None,
            bundle=bundle,
        )
        finite = np.isfinite(values)
        if vote_input.linear:
            crossed: tuple[np.ndarray, ...] = ()
        else:
            at_most = vote_input.direction == "at_most"
            with np.errstate(invalid="ignore"):
                crossed = tuple(
                    finite & ((values <= step.level) if at_most else (values >= step.level))
                    for step in vote_input.steps
                )
        if not evidence:
            return None, crossed, values
        trace = tuple(
            float(item) if ok else None
            for item, ok in zip(values.tolist(), finite.tolist(), strict=True)
        )
        return trace, crossed, values
    length = len(frame.time_ms)
    count = np.zeros(length, dtype=np.int64)
    for index, raw in enumerate(vote_input.count_of):
        mask = evaluate_predicate(
            parse_predicate(raw, f"{path}.count.of[{index}]"),
            frame,
            side,
            context=context,
            identity=identities[index] if identities is not None else None,
            bundle=bundle,
        )
        if len(mask) != length:
            raise InvalidRequestError(
                "weighted vote predicate mask length mismatch", input_id=vote_input.input_id
            )
        count += mask
    crossed = tuple(count >= step.level for step in vote_input.steps)
    return (tuple(count.tolist()) if evidence else None), crossed, None


def _linear_ladder(vote_input: VoteInput, values: np.ndarray) -> np.ndarray:
    """Ladder value of a linear input: the points (level, weight) sorted by
    level joined by straight lines, end values outside, 0 where missing
    (design D2; `numpy.interp`, as the research black curve)."""

    points = sorted((float(step.level), step.weight or 0) for step in vote_input.steps)
    levels = np.array([level for level, _ in points], dtype=np.float64)
    weights = np.array([weight / WEIGHT_SCALE for _, weight in points], dtype=np.float64)
    finite = np.isfinite(values)
    return np.where(finite, np.interp(np.where(finite, values, levels[0]), levels, weights), 0.0)


def exponent_weight(values: np.ndarray, exponent: Exponent) -> np.ndarray:
    """`(exp(k x) - 1) / (exp(k e_v) - 1)` in float64, in this form (not
    expm1) to equal research bit for bit (design D1)."""

    weights = (np.exp(exponent.k * values) - 1.0) / (np.exp(exponent.k * exponent.e_v) - 1.0)
    return np.asarray(weights, dtype=np.float64)


def _scaled_trace(values: np.ndarray) -> tuple[float, ...]:
    # int64 below 2**53 converts exactly, so this division is correctly
    # rounded: the nearest float of the exact decimal (design D6).
    return tuple((values.astype(np.float64) / float(WEIGHT_SCALE)).tolist())


def _exact(weight: int | float, scaled: bool) -> Fraction:
    return Fraction(int(weight), WEIGHT_SCALE) if scaled else Fraction(float(weight))


# Bars whose float score is this close to the threshold are decided again in
# exact rational arithmetic (design D3); float error of a sum of a few dozen
# weights is many orders of magnitude below it.
_EXACT_BAND = 1e-6


def _weighted_vote_compute(
    spec: WeightedVoteSpec,
    frame: FeatureFrameLike,
    side: str,
    *,
    context: EvaluationContext | None,
    inputs: tuple[tuple[PredicateIdentity, ...], ...] | None,
    bundle: ContextBundle | None = None,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    """Local mask and evidence of one weighted vote, vectorized, in exact
    integer arithmetic (units of 10**-9). The memoized value carries the
    labels: they are part of the vote node identity (design D8).

    With exponent or linear inputs (exponent-vote-weighting-v1) weights are
    floats: the score is summed in float64 and every bar near the threshold
    is decided again exactly over rationals (design D3).

    In a context without evidence (execution projection) the per-bar
    trace is not built and the evidence dict is empty: ~20 inputs times
    three Python tuples over every bar are what dominates memory, and
    nothing on that path reads them. The mask is identical either way."""

    length = len(frame.time_ms)
    evidence = context is None or context.evidence
    floating = any(item.exponent is not None or item.linear for item in spec.inputs())
    trace: dict[str, tuple[object, ...]] = {}
    voter_weights: list[np.ndarray] = []
    voter_vetoes: list[np.ndarray] = []
    # Per voter, per input: (weight array, scaled-integer flag) for the exact pass.
    voter_parts: list[list[tuple[np.ndarray, bool]]] = []
    input_index = 0
    for voter in spec.voters:
        voter_weight = np.zeros(length, dtype=np.float64 if floating else np.int64)
        voter_veto = np.zeros(length, dtype=bool)
        parts: list[tuple[np.ndarray, bool]] = []
        for vote_input in voter.inputs:
            path = f"setup[{spec.instance_id}].{vote_input.input_id}"
            identities = inputs[input_index] if inputs is not None else None
            value_trace, crossed, values = _vote_input_crossings(
                vote_input,
                path,
                frame,
                side,
                context=context,
                identities=identities,
                bundle=bundle,
                evidence=evidence,
            )
            input_index += 1
            veto = np.zeros(length, dtype=bool)
            level_value: np.ndarray | None = None
            if vote_input.linear:
                assert values is not None
                level_value = _linear_ladder(vote_input, values)
                weight: np.ndarray = level_value
                scaled = False
            else:
                weight = np.zeros(length, dtype=np.int64)
                for step, mask in zip(vote_input.steps, crossed, strict=True):
                    if step.weight is None:
                        veto |= mask
                    else:
                        weight = np.where(mask, np.maximum(weight, step.weight), weight)
                scaled = True
            if vote_input.exponent is not None:
                if scaled:
                    level_value = weight.astype(np.float64) / float(WEIGHT_SCALE)
                assert level_value is not None
                weight = exponent_weight(level_value, vote_input.exponent)
                scaled = False
            if value_trace is not None:
                trace[f"input:{vote_input.input_id}:value"] = value_trace
                if vote_input.exponent is not None:
                    assert level_value is not None
                    trace[f"input:{vote_input.input_id}:level_value"] = tuple(level_value.tolist())
                trace[f"input:{vote_input.input_id}:weight"] = (
                    _scaled_trace(weight) if scaled else tuple(weight.astype(np.float64).tolist())
                )
                trace[f"input:{vote_input.input_id}:veto"] = tuple(veto.tolist())
            parts.append((weight, scaled))
            as_voter = (
                weight.astype(np.float64) / float(WEIGHT_SCALE) if floating and scaled else weight
            )
            voter_weight = np.maximum(voter_weight, as_voter)
            voter_veto |= veto
        if evidence:
            trace[f"voter:{voter.voter_id}:weight"] = (
                tuple(voter_weight.tolist()) if floating else _scaled_trace(voter_weight)
            )
            trace[f"voter:{voter.voter_id}:veto"] = tuple(voter_veto.tolist())
        voter_weights.append(voter_weight)
        voter_vetoes.append(voter_veto)
        voter_parts.append(parts)
    # One row per voter (voters are never empty); a zero-bar frame gives (n, 0).
    score = np.sum(np.stack(voter_weights), axis=0)
    vetoes = np.stack(voter_vetoes)
    any_veto = np.logical_or.reduce(vetoes, axis=0, initial=False)
    if floating:
        threshold = spec.threshold / WEIGHT_SCALE
        by_score = score >= threshold
        exact_threshold = Fraction(spec.threshold, WEIGHT_SCALE)
        for bar in np.flatnonzero(np.abs(score - threshold) <= _EXACT_BAND).tolist():
            total = sum(
                (max(_exact(array[bar], flag) for array, flag in parts) for parts in voter_parts),
                Fraction(0),
            )
            by_score[bar] = total >= exact_threshold
    else:
        by_score = score >= spec.threshold
    if evidence:
        labels = np.array(
            [f"veto:{voter.voter_id}" for voter in spec.voters] + ["score", None], dtype=object
        )
        count = len(spec.voters)
        reason = np.where(any_veto, np.argmax(vetoes, axis=0), np.where(by_score, count, count + 1))
        trace["score"] = tuple(score.tolist()) if floating else _scaled_trace(score)
        trace["blocked_by"] = tuple(labels[reason].tolist())
    return tuple((~(any_veto | by_score)).tolist()), trace


def _setup(
    item: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    records: tuple[ContextConsumptionRecord, ...],
    *,
    context: EvaluationContext | None = None,
    identity: SetupIdentity | None = None,
    bundle: ContextBundle | None = None,
) -> SetupMask:
    component_id, instance_id, params = _setup_head(item, side)
    if component_id == COMPOSITE_SETUP:
        spec = parse_composite_setup(item, f"setup[{instance_id}]")
        core = compute_through(
            context,
            identity.local if identity else None,
            functools.partial(
                _composite_core,
                spec,
                frame,
                plan,
                side,
                context=context,
                children=identity.children if identity else None,
                bundle=bundle,
            ),
        )
        local, trace = core.local, _composite_trace(spec, core)
    elif component_id == WEIGHTED_VOTE_SETUP:
        local, trace = compute_through(
            context,
            identity.local if identity else None,
            functools.partial(
                _weighted_vote_compute,
                parse_weighted_vote_setup(item, f"setup[{instance_id}]"),
                frame,
                side,
                context=context,
                inputs=identity.vote_inputs if identity else None,
                bundle=bundle,
            ),
        )
    else:
        compute = _semantic_setup_compute(
            component_id, instance_id, params, frame, plan, side, context=context, identity=identity
        )
        local, trace = compute_through(context, identity.local if identity else None, compute)
    gate = _gate_for(records, instance_id=instance_id, side=side)
    final = compute_through(
        context,
        identity.final if identity else None,
        functools.partial(_apply_gate, local, gate),
    )
    return SetupMask(
        component_id=component_id,
        instance_id=instance_id,
        side=side,
        local_setup_allowed=local,
        context_gate_allowed=gate,
        final_setup_allowed=final,
        # A private dict per consumer: a memoized trace is shared by every
        # candidate that reads it and must never be handed out mutable.
        trace=dict(trace),
    )


def _setup_items(raw_spec: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw_setups = _sequence(raw_spec.get("setups", []), "raw_spec.setups")
    return tuple(
        _mapping(item, f"raw_spec.setups[{index}]") for index, item in enumerate(raw_setups)
    )


def evaluate_setups(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    context_records: tuple[ContextConsumptionRecord, ...],
    direction_blockers: tuple[SideDirectionBlockers, ...],
    *,
    context: EvaluationContext | None = None,
    identities: tuple[SideSetupIdentity, ...] | None = None,
    bundle: ContextBundle | None = None,
) -> tuple[SideSetupEvaluation, ...]:
    """`context` + `identities` (the `resolve_setups` twin of this exact
    call; batch-computation-reuse 4.6): every setup-component, width-prefix
    and mask-composition node is computed through the context's memo at the
    point it is computed today. Without them, everything computes directly."""

    setup_items = _setup_items(raw_spec)
    if identities is not None and (
        tuple(item.side for item in identities) != tuple(p.side for p in direction_blockers)
        or any(len(item.setups) != len(setup_items) for item in identities)
    ):
        identities = None  # not this call's twin: never memoize on a mismatch
    outputs: list[SideSetupEvaluation] = []
    for index, prior in enumerate(direction_blockers):
        ids = identities[index] if identities is not None else None
        masks = tuple(
            _setup(
                item,
                frame,
                plan,
                prior.side,
                context_records,
                context=context,
                identity=ids.setups[item_index] if ids else None,
                bundle=bundle,
            )
            for item_index, item in enumerate(setup_items)
        )
        setups_ok = compute_through(
            context,
            ids.setups_ok if ids else None,
            functools.partial(
                _combine_setup_masks,
                tuple(mask.final_setup_allowed for mask in masks),
                len(frame.time_ms),
            ),
        )
        pre_trigger = compute_through(
            context,
            ids.pre_trigger_allowed if ids else None,
            functools.partial(and_pair, prior.pre_setup_allowed, setups_ok),
        )
        outputs.append(SideSetupEvaluation(prior.side, masks, setups_ok, pre_trigger))
    return tuple(outputs)


# -- semantic node identity (batch-computation-reuse group 3) -----------------

SETUP_NODE_VERSION = 1


def _feature_node(feature_ids: Mapping[str, NodeSpec], output_id: str) -> NodeSpec:
    try:
        return feature_ids[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc


@dataclass(frozen=True, slots=True)
class SetupIdentity:
    """Identities of one setup item for one side. `local` covers
    `local_setup_allowed` + `trace`; `final` covers `final_setup_allowed`.
    `width_prefix` is set only for the width setups: the side-free,
    threshold-free `(current_width_atr, recent_max_width_atr)` prefix of
    `anchor_stack_width_setup`, or the `width_atr` node of
    `anchor_stack_width_band_setup`."""

    instance_id: str
    side: str
    local: NodeSpec
    final: NodeSpec
    width_prefix: NodeSpec | None = None
    children: tuple[SetupIdentity, ...] = ()
    # Set only for a composite predicate child (its column nodes).
    predicate: PredicateIdentity | None = None
    # Weighted vote only: per input, the predicate identities it reads, and
    # every consumption its compute makes, in order (design D8).
    vote_inputs: tuple[tuple[PredicateIdentity, ...], ...] = ()
    vote_consumptions: tuple[NodeSpec, ...] = ()


def resolve_setup_local(
    item: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
) -> tuple[NodeSpec, NodeSpec | None]:
    """`(local identity, width prefix identity or None)` for one setup item.

    Untouched-anchor and bounce-counter read the side; the width setup does
    not (its local identity is the same for both sides). `instance_id` is a
    label: it selects plan columns and the gate, never enters an identity.
    """

    component_id, instance_id, params = _setup_head(item, side)
    kind = f"setup.{component_id}"
    if component_id in (COMPOSITE_SETUP, WEIGHTED_VOTE_SETUP):
        raise InvalidRequestError(f"{component_id} resolves through resolve_setup_identity")
    if component_id == "untouched_anchor_setup":
        lookback, active_bars = _untouched_anchor_params(params)
        return (
            node_spec(
                kind,
                version=SETUP_NODE_VERSION,
                params={"lookback": lookback, "active_bars": active_bars},
                upstream={"anchor": _feature_node(feature_ids, plan.anchor_columns["anchor"])},
                side=side,
            ),
            None,
        )
    columns = _setup_columns(plan, instance_id)
    if component_id == "ema_bounce_counter_setup":
        max_bounces, raw_touch_mode, touch_lookback, start_confirm, break_confirm = (
            _ema_bounce_counter_params(params)
        )
        return (
            node_spec(
                kind,
                version=SETUP_NODE_VERSION,
                params={
                    "max_bounces": max_bounces,
                    "raw_touch_mode": raw_touch_mode,
                    "touch_lookback_bars": touch_lookback,
                    "trend_start_confirmation_bars": start_confirm,
                    "trend_break_confirmation_bars": break_confirm,
                },
                upstream={
                    role: _feature_node(feature_ids, columns[role])
                    for role in ("fast", "anchor", "slow")
                },
                side=side,
            ),
            None,
        )
    if component_id == WIDTH_BAND_SETUP:
        band = parse_width_band_params(params)
        fast_node = _feature_node(feature_ids, columns["fast"])
        slow_node = _feature_node(feature_ids, columns["slow"])
        atr_node = _feature_node(feature_ids, columns["atr"])
        width_node = node_spec(
            "setup.anchor_stack_width_band.width",
            version=SETUP_NODE_VERSION,
            params={},
            upstream={"fast": fast_node, "slow": slow_node, "atr": atr_node},
        )
        band_params: dict[str, Any] = {"min_width_atr": band.min_width_atr}
        if band.max_width_atr is not None:
            band_params["max_width_atr"] = band.max_width_atr
        return (
            node_spec(
                kind,
                version=SETUP_NODE_VERSION,
                params=band_params,
                upstream={"width": width_node},
            ),
            width_node,
        )
    min_current, min_recent, lookback = _anchor_stack_width_params(params)
    fast = _feature_node(feature_ids, columns["fast"])
    anchor = _feature_node(feature_ids, columns["anchor"])
    slow = _feature_node(feature_ids, columns["slow"])
    atr = _feature_node(feature_ids, columns["atr"])
    prefix = node_spec(
        "setup.anchor_stack_width.prefix",
        version=SETUP_NODE_VERSION,
        params={"width_lookback_bars": lookback},
        upstream={"fast": fast, "slow": slow, "atr": atr},
    )
    local = node_spec(
        kind,
        version=SETUP_NODE_VERSION,
        params={"min_current_width_atr": min_current, "min_recent_width_atr": min_recent},
        upstream={"prefix": prefix, "fast": fast, "anchor": anchor, "slow": slow, "atr": atr},
    )
    return local, prefix


def _resolve_composite(
    item: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
    contexts: Mapping[str, NodeSpec] | None = None,
) -> tuple[NodeSpec, tuple[SetupIdentity, ...]]:
    """`(composite local identity, child identities)`. Children are ordered
    upstream roles and paths reference them by position, so neither
    `instance_id`, `child_id` nor `path_id` enters any identity."""

    _component_id, instance_id, _params = _setup_head(item, side)
    spec = parse_composite_setup(item, f"setup[{instance_id}]")
    positions = {child.child_id: index for index, child in enumerate(spec.children)}
    children: list[SetupIdentity] = []
    for child in spec.children:
        if child.predicate is not None:
            predicate = resolve_predicate(
                parse_predicate(child.predicate, f"setup[{instance_id}].{child.child_id}"),
                feature_ids,
                side,
                contexts,
            )
            children.append(
                SetupIdentity(
                    instance_id=child_instance_key(spec.instance_id, child.child_id),
                    side=side,
                    local=predicate.local,
                    final=predicate.local,
                    predicate=predicate,
                )
            )
            continue
        child_item = child_setup_item(spec, child)
        local, prefix = resolve_setup_local(child_item, plan, feature_ids, side)
        children.append(
            SetupIdentity(
                instance_id=child_item["instance_id"],
                side=side,
                local=local,
                final=local,
                width_prefix=prefix,
            )
        )
    paths = tuple(
        (
            tuple(positions[ref] for ref in composite_path.require),
            composite_path.at_least_k,
            tuple(positions[ref] for ref in composite_path.at_least_of),
        )
        for composite_path in spec.paths
    )
    local = node_spec(
        f"setup.{COMPOSITE_SETUP}",
        version=SETUP_NODE_VERSION,
        params={"paths": paths},
        upstream={f"child_{index}": child.local for index, child in enumerate(children)},
    )
    return local, tuple(children)


def _vote_step_param(step: Any) -> tuple[object, ...]:
    return (
        step.level,
        None if step.weight is None else scaled_to_text(step.weight),
        step.weight is None,
    )


def _vote_input_param(vote_input: VoteInput) -> tuple[object, ...]:
    """Normalized identity params of one input. Inputs without the
    exponent-vote-weighting-v1 keys keep their former tuple byte for byte
    (design D6)."""

    base: tuple[object, ...] = (
        vote_input.input_id,
        "operand" if vote_input.operand_predicate is not None else "count",
        vote_input.direction,
        tuple(_vote_step_param(step) for step in vote_input.steps),
    )
    if not vote_input.has_extensions():
        return base
    exponent = vote_input.exponent
    return base + (
        (
            ("between", vote_input.between),
            ("exponent", None if exponent is None else (repr(exponent.k), repr(exponent.e_v))),
        ),
    )


def _resolve_weighted_vote(
    item: Mapping[str, Any],
    feature_ids: Mapping[str, NodeSpec],
    side: str,
    contexts: Mapping[str, NodeSpec] | None = None,
) -> tuple[NodeSpec, tuple[tuple[PredicateIdentity, ...], ...], tuple[NodeSpec, ...]]:
    """`(vote node, per-input predicate identities, inner consumptions)`.

    The vote node carries the normalized table with its labels and declared
    order (they name the evidence) and the side; its upstream are the
    predicate-layer nodes of the inputs, which keep their own identities and
    are shared with composites and other votes (design D8)."""

    _component_id, instance_id, _params = _setup_head(item, side)
    spec = parse_weighted_vote_setup(item, f"setup[{instance_id}]")
    inputs: list[tuple[PredicateIdentity, ...]] = []
    consumed: list[NodeSpec] = []
    upstream: dict[str, NodeSpec] = {}
    for input_index, vote_input in enumerate(spec.inputs()):
        path = f"setup[{instance_id}].{vote_input.input_id}"
        identities = tuple(
            resolve_predicate(parse_predicate(raw, path), feature_ids, side, contexts)
            for raw in vote_input.predicates()
        )
        inputs.append(identities)
        for predicate_index, identity in enumerate(identities):
            upstream[f"input_{input_index}_{predicate_index}"] = identity.local
            if vote_input.operand_predicate is None:
                consumed.append(identity.local)
            consumed += identity.nested
    voters = tuple(
        (
            voter.voter_id,
            voter.role,
            tuple(_vote_input_param(vote_input) for vote_input in voter.inputs),
        )
        for voter in spec.voters
    )
    local = node_spec(
        "setup.weighted_vote",
        version=SETUP_NODE_VERSION,
        params={"threshold": scaled_to_text(spec.threshold), "voters": voters},
        upstream=upstream,
        side=side,
    )
    return local, tuple(inputs), tuple(consumed)


def resolve_setup_identity_for_side(
    item: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    gates: tuple[GateIdentity, ...],
    side: str,
    contexts: Mapping[str, NodeSpec] | None = None,
) -> SetupIdentity:
    """The full identity of one setup item for one side (plain or composite)."""

    component_id, instance_id = _setup_identity(item)
    gate = gate_node_for(gates, role="setup", instance_id=instance_id, side=side)
    if component_id == COMPOSITE_SETUP:
        local, children = _resolve_composite(item, plan, feature_ids, side, contexts)
        return SetupIdentity(
            instance_id=instance_id,
            side=side,
            local=local,
            final=gated_mask_node(local, gate),
            children=children,
        )
    if component_id == WEIGHTED_VOTE_SETUP:
        local, vote_inputs, vote_consumptions = _resolve_weighted_vote(
            item, feature_ids, side, contexts
        )
        return SetupIdentity(
            instance_id=instance_id,
            side=side,
            local=local,
            final=gated_mask_node(local, gate),
            vote_inputs=vote_inputs,
            vote_consumptions=vote_consumptions,
        )
    local, prefix = resolve_setup_local(item, plan, feature_ids, side)
    return SetupIdentity(
        instance_id=instance_id,
        side=side,
        local=local,
        final=gated_mask_node(local, gate),
        width_prefix=prefix,
    )


@dataclass(frozen=True, slots=True)
class SideSetupIdentity:
    side: str
    setups: tuple[SetupIdentity, ...]
    setups_ok: NodeSpec
    pre_trigger_allowed: NodeSpec


def resolve_setups(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    gates: tuple[GateIdentity, ...],
    direction_blockers: tuple[SideDirectionBlockerIdentity, ...],
    contexts: Mapping[str, NodeSpec] | None = None,
) -> tuple[SideSetupIdentity, ...]:
    """Identity twin of `evaluate_setups` (per side of `direction_blockers`)."""

    setup_items = _setup_items(raw_spec)
    outputs: list[SideSetupIdentity] = []
    for prior in direction_blockers:
        setups = [
            resolve_setup_identity_for_side(item, plan, feature_ids, gates, prior.side, contexts)
            for item in setup_items
        ]
        setups_ok = and_masks_node("mask.all", tuple(setup.final for setup in setups))
        outputs.append(
            SideSetupIdentity(
                side=prior.side,
                setups=tuple(setups),
                setups_ok=setups_ok,
                pre_trigger_allowed=pairwise_and_node(
                    "mask.all", prior.pre_setup_allowed, setups_ok
                ),
            )
        )
    return tuple(outputs)
