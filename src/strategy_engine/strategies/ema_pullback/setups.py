"""BBB-compatible ema_pullback setup components and composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
    GateIdentity,
)
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    SideDirectionBlockerIdentity,
    SideDirectionBlockers,
    and_masks_node,
    gate_node_for,
    gated_mask_node,
    pairwise_and_node,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    SETUP_SUPPORTED,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_setup_identity as _setup_identity,
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
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    min_current, min_recent, lookback = _anchor_stack_width_params(params)
    fast = _float_series(frame, columns["fast"])
    anchor = _float_series(frame, columns["anchor"])
    slow = _float_series(frame, columns["slow"])
    atr = _float_series(frame, columns["atr"])
    width_atr, recent_max = _anchor_stack_width_prefix(fast, slow, atr, lookback)
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


def _setup(
    item: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    records: tuple[ContextConsumptionRecord, ...],
) -> SetupMask:
    component_id, instance_id, params = _setup_head(item, side)
    if component_id == "untouched_anchor_setup":
        local, trace = _untouched_anchor(frame, plan.anchor_columns["anchor"], params, side)
    elif component_id == "ema_bounce_counter_setup":
        columns = _setup_columns(plan, instance_id)
        local, trace = _ema_bounce_counter(frame, columns, params, side)
    else:
        columns = _setup_columns(plan, instance_id)
        local, trace = _anchor_stack_width(frame, columns, params)
    gate = _gate_for(records, instance_id=instance_id, side=side)
    return SetupMask(
        component_id=component_id,
        instance_id=instance_id,
        side=side,
        local_setup_allowed=local,
        context_gate_allowed=gate,
        final_setup_allowed=_apply_gate(local, gate),
        trace=trace,
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
) -> tuple[SideSetupEvaluation, ...]:
    setup_items = _setup_items(raw_spec)
    outputs: list[SideSetupEvaluation] = []
    for prior in direction_blockers:
        masks = tuple(
            _setup(item, frame, plan, prior.side, context_records) for item in setup_items
        )
        setups_ok = _combine_setup_masks(
            tuple(mask.final_setup_allowed for mask in masks), len(frame.time_ms)
        )
        pre_trigger = tuple(
            allowed and setup_ok
            for allowed, setup_ok in zip(prior.pre_setup_allowed, setups_ok, strict=True)
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
    `width_prefix` is set only for the width setup: its side-free,
    threshold-free `(current_width_atr, recent_max_width_atr)` prefix."""

    instance_id: str
    side: str
    local: NodeSpec
    final: NodeSpec
    width_prefix: NodeSpec | None = None


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
) -> tuple[SideSetupIdentity, ...]:
    """Identity twin of `evaluate_setups` (per side of `direction_blockers`)."""

    setup_items = _setup_items(raw_spec)
    outputs: list[SideSetupIdentity] = []
    for prior in direction_blockers:
        setups: list[SetupIdentity] = []
        for item in setup_items:
            local, prefix = resolve_setup_local(item, plan, feature_ids, prior.side)
            _component_id, instance_id = _setup_identity(item)
            gate = gate_node_for(gates, role="setup", instance_id=instance_id, side=prior.side)
            setups.append(
                SetupIdentity(
                    instance_id=instance_id,
                    side=prior.side,
                    local=local,
                    final=gated_mask_node(local, gate),
                    width_prefix=prefix,
                )
            )
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
