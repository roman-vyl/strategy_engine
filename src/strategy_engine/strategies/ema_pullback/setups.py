"""BBB-compatible ema_pullback setup components and composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
)
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    SideDirectionBlockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
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


def _float_series(frame: FeatureFrame, output_id: str) -> tuple[float, ...]:
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc
    return tuple(float("nan") if value is None else float(value) for value in values)


def _market_values(frame: FeatureFrame, field: str) -> tuple[float, ...]:
    if len(frame.market_bars) != len(frame.time_ms):
        raise InvalidRequestError("market bars unavailable for setup evaluation")
    return tuple(float(getattr(bar, field)) for bar in frame.market_bars)


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


def _untouched_anchor(
    frame: FeatureFrame,
    anchor_id: str,
    params: Mapping[str, Any],
    side: str,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    lookback = int(params.get("lookback", 50))
    active_bars = int(params.get("active_bars", 3))
    if lookback <= 0 or active_bars <= 0:
        raise InvalidRequestError("untouched anchor setup periods must be positive")
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
    untouched_prior: list[bool] = []
    for index in range(len(touch)):
        if index < lookback:
            untouched_prior.append(False)
            continue
        untouched_prior.append(not any(touch[index - lookback : index]))
    armed_pre = tuple(
        ok and untouched and not touched
        for ok, untouched, touched in zip(side_ok, untouched_prior, touch, strict=True)
    )
    first_touch = tuple(
        touched and untouched for touched, untouched in zip(touch, untouched_prior, strict=True)
    )
    touch_active = tuple(
        any(first_touch[max(0, index - active_bars + 1) : index + 1])
        for index in range(len(first_touch))
    )
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


def _ema_bounce_counter(
    frame: FeatureFrame,
    columns: Mapping[str, str],
    params: Mapping[str, Any],
    side: str,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    max_bounces = int(params.get("max_bounces", 3))
    raw_touch_mode = str(params.get("raw_touch_mode", "range_cross"))
    touch_lookback = int(params.get("touch_lookback_bars", 10))
    start_confirm = int(params.get("trend_start_confirmation_bars", 1))
    break_confirm = int(params.get("trend_break_confirmation_bars", 1))
    if max_bounces <= 0 or touch_lookback <= 0 or start_confirm <= 0 or break_confirm <= 0:
        raise InvalidRequestError("ema bounce counter parameters must be positive")
    if raw_touch_mode != "range_cross":
        raise InvalidRequestError("raw_touch_mode must be range_cross")
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


def _anchor_stack_width(
    frame: FeatureFrame,
    columns: Mapping[str, str],
    params: Mapping[str, Any],
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    min_current = float(params.get("min_current_width_atr", 2.0))
    min_recent = float(params.get("min_recent_width_atr", 4.0))
    lookback = int(params.get("width_lookback_bars", 80))
    if min_current <= 0 or min_recent <= 0 or lookback <= 0:
        raise InvalidRequestError("anchor stack width parameters must be positive")
    fast = _float_series(frame, columns["fast"])
    anchor = _float_series(frame, columns["anchor"])
    slow = _float_series(frame, columns["slow"])
    atr = _float_series(frame, columns["atr"])
    width_atr = tuple(
        abs(f - s) / a if all(isfinite(v) for v in (f, s, a)) and a > 0 else float("nan")
        for f, s, a in zip(fast, slow, atr, strict=True)
    )
    recent_max: list[float] = []
    allowed: list[bool] = []
    reasons: list[str] = []
    current_ok: list[bool] = []
    recent_ok: list[bool] = []
    for index, current in enumerate(width_atr):
        window = width_atr[index - lookback + 1 : index + 1] if index + 1 >= lookback else ()
        recent = (
            max(window) if window and all(isfinite(value) for value in window) else float("nan")
        )
        recent_max.append(recent)
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


def _setup(
    item: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    side: str,
    records: tuple[ContextConsumptionRecord, ...],
) -> SetupMask:
    component_id = str(item.get("component_id", ""))
    instance_id = str(item.get("instance_id", component_id))
    params = _mapping(item.get("params", {}), f"setup[{instance_id}].params")
    if side not in _VALID_SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    if component_id == "untouched_anchor_setup":
        local, trace = _untouched_anchor(frame, plan.anchor_columns["anchor"], params, side)
    elif component_id == "ema_bounce_counter_setup":
        columns = plan.setup_columns_by_instance_id.get(instance_id)
        if columns is None:
            raise InvalidRequestError("missing setup feature mapping", instance_id=instance_id)
        local, trace = _ema_bounce_counter(frame, columns, params, side)
    elif component_id == "anchor_stack_width_setup":
        columns = plan.setup_columns_by_instance_id.get(instance_id)
        if columns is None:
            raise InvalidRequestError("missing setup feature mapping", instance_id=instance_id)
        local, trace = _anchor_stack_width(frame, columns, params)
    else:
        raise InvalidRequestError("unsupported setup component", component_id=component_id)
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


def evaluate_setups(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    context_records: tuple[ContextConsumptionRecord, ...],
    direction_blockers: tuple[SideDirectionBlockers, ...],
) -> tuple[SideSetupEvaluation, ...]:
    raw_setups = _sequence(raw_spec.get("setups", []), "raw_spec.setups")
    setup_items = tuple(
        _mapping(item, f"raw_spec.setups[{index}]") for index, item in enumerate(raw_setups)
    )
    outputs: list[SideSetupEvaluation] = []
    for prior in direction_blockers:
        masks = tuple(
            _setup(item, frame, plan, prior.side, context_records) for item in setup_items
        )
        if masks:
            setups_ok = tuple(
                all(mask.final_setup_allowed[index] for mask in masks)
                for index in range(len(frame.time_ms))
            )
        else:
            setups_ok = tuple(True for _ in frame.time_ms)
        pre_trigger = tuple(
            allowed and setup_ok
            for allowed, setup_ok in zip(prior.pre_setup_allowed, setups_ok, strict=True)
        )
        outputs.append(SideSetupEvaluation(prior.side, masks, setups_ok, pre_trigger))
    return tuple(outputs)
