"""BBB-compatible direction and blocker semantics for ema_pullback."""

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
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan

_VALID_SIDES = {"long", "short"}


@dataclass(frozen=True, slots=True)
class ComponentMask:
    role: str
    component_id: str
    instance_id: str
    side: str
    intrinsic_allowed: tuple[bool, ...]
    context_allowed: tuple[bool, ...] | None
    allowed: tuple[bool, ...]
    trace: dict[str, tuple[object, ...]]

    def to_wire(self) -> dict[str, object]:
        return {
            "role": self.role,
            "component_id": self.component_id,
            "instance_id": self.instance_id,
            "side": self.side,
            "intrinsic_allowed": list(self.intrinsic_allowed),
            "context_allowed": (
                list(self.context_allowed) if self.context_allowed is not None else None
            ),
            "allowed": list(self.allowed),
            "trace": {key: list(values) for key, values in self.trace.items()},
            "counters": {
                "intrinsic_allowed_count": sum(self.intrinsic_allowed),
                "intrinsic_blocked_count": len(self.intrinsic_allowed)
                - sum(self.intrinsic_allowed),
                "allowed_count": sum(self.allowed),
                "blocked_count": len(self.allowed) - sum(self.allowed),
            },
        }


@dataclass(frozen=True, slots=True)
class SideDirectionBlockers:
    side: str
    direction: ComponentMask
    blockers: tuple[ComponentMask, ...]
    blockers_ok: tuple[bool, ...]
    pre_setup_allowed: tuple[bool, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "side": self.side,
            "direction": self.direction.to_wire(),
            "blockers": [item.to_wire() for item in self.blockers],
            "blockers_ok": list(self.blockers_ok),
            "pre_setup_allowed": list(self.pre_setup_allowed),
        }


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _sequence(value: object, path: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(value)


def _enabled_sides(raw_spec: Mapping[str, Any]) -> tuple[str, ...]:
    raw: object = raw_spec.get("trade_sides", ["long"])
    if isinstance(raw, Mapping):
        raw = raw.get("enabled", ["long"])
    sides = tuple(str(item) for item in _sequence(raw, "raw_spec.trade_sides"))
    if not sides or any(side not in _VALID_SIDES for side in sides):
        raise InvalidRequestError("raw_spec.trade_sides must contain long/short")
    return sides


def _float_series(frame: FeatureFrame, output_id: str) -> tuple[float, ...]:
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc
    return tuple(float("nan") if value is None else float(value) for value in values)


def _gate_for(
    records: tuple[ContextConsumptionRecord, ...],
    *,
    role: str,
    instance_id: str,
    side: str,
) -> tuple[bool, ...] | None:
    for record in records:
        if record.role == role and record.instance_id == instance_id and record.side == side:
            return record.allowed
    return None


def _apply_gate(intrinsic: tuple[bool, ...], gate: tuple[bool, ...] | None) -> tuple[bool, ...]:
    if gate is None:
        return intrinsic
    if len(gate) != len(intrinsic):
        raise InvalidRequestError("context gate length does not match component mask")
    return tuple(left and right for left, right in zip(intrinsic, gate, strict=True))


def _direction(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    side: str,
) -> ComponentMask:
    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    component_id = str(components.get("direction", "ema_anchor_stack_trend"))
    if component_id != "ema_anchor_stack_trend":
        raise InvalidRequestError("unsupported direction component", component_id=component_id)
    fast = _float_series(frame, plan.anchor_columns["fast"])
    anchor = _float_series(frame, plan.anchor_columns["anchor"])
    slow = _float_series(frame, plan.anchor_columns["slow"])
    if side == "long":
        first = tuple(a > b for a, b in zip(fast, anchor, strict=True))
        second = tuple(a > b for a, b in zip(anchor, slow, strict=True))
    else:
        first = tuple(a < b for a, b in zip(fast, anchor, strict=True))
        second = tuple(a < b for a, b in zip(anchor, slow, strict=True))
    allowed = tuple(a and b for a, b in zip(first, second, strict=True))
    return ComponentMask(
        role="direction",
        component_id=component_id,
        instance_id=component_id,
        side=side,
        intrinsic_allowed=allowed,
        context_allowed=None,
        allowed=allowed,
        trace={"fast_gt_anchor": first, "anchor_gt_slow": second},
    )


def _rsi_blocker(
    item: Mapping[str, Any], frame: FeatureFrame, plan: EmaPullbackFeaturePlan, side: str
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    rsi_spec = _mapping(item.get("rsi"), "blocker.rsi")
    timeframe = str(rsi_spec.get("timeframe", "base"))
    period = int(rsi_spec.get("period", 14))
    output_id = plan.rsi_columns.get((timeframe, period))
    if output_id is None:
        raise InvalidRequestError("missing RSI mapping for blocker")
    values = _float_series(frame, output_id)
    lookback = int(item.get("lookback", 20))
    if lookback <= 0:
        raise InvalidRequestError("blocker lookback must be positive")
    threshold = (
        float(item.get("long_block_above", 80.0))
        if side == "long"
        else float(item.get("short_block_below", 20.0))
    )
    extreme: list[bool] = []
    for value in values:
        extreme.append(
            False
            if not isfinite(value)
            else value > threshold
            if side == "long"
            else value < threshold
        )
    seen: list[bool] = []
    for index in range(len(extreme)):
        start = max(0, index - lookback + 1)
        seen.append(any(extreme[start : index + 1]))
    allowed = tuple(not value for value in seen)
    return allowed, {"rsi": tuple(values), "extreme_seen": tuple(seen)}


def _trend_strength_blocker(
    item: Mapping[str, Any], frame: FeatureFrame, plan: EmaPullbackFeaturePlan, side: str
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    params = _mapping(item.get("trend_strength"), "blocker.trend_strength")
    timeframe = str(params.get("timeframe", "base"))
    period = int(params.get("adx_period", 14))
    columns = plan.adx_dmi_columns.get((timeframe, period))
    if columns is None:
        raise InvalidRequestError("missing ADX/DMI mapping for blocker")
    adx = _float_series(frame, columns["adx"])
    di_plus = _float_series(frame, columns["di_plus"])
    di_minus = _float_series(frame, columns["di_minus"])
    min_peak = float(params.get("min_adx_peak", 25.0))
    peak_lookback = int(params.get("peak_lookback_bars", 60))
    max_since = int(params.get("max_bars_since_peak", 30))
    min_current = float(params.get("min_current_adx", 15.0))
    require_alignment = bool(params.get("require_di_alignment_on_peak", True))
    block_flip = bool(params.get("block_on_opposite_di_flip", True))
    margin = float(params.get("opposite_di_margin", 0.0))
    allowed: list[bool] = []
    reasons: list[str] = []
    peak_indices: list[int] = []
    bars_since: list[int] = []
    for index in range(len(adx)):
        if not all(isfinite(value) for value in (adx[index], di_plus[index], di_minus[index])):
            allowed.append(False)
            reasons.append("indicator_not_ready")
            peak_indices.append(-1)
            bars_since.append(-1)
            continue
        start = max(0, index - peak_lookback + 1)
        peak_index = -1
        for candidate in range(index, start - 1, -1):
            if not all(
                isfinite(value)
                for value in (adx[candidate], di_plus[candidate], di_minus[candidate])
            ):
                continue
            aligned = (
                di_plus[candidate] > di_minus[candidate]
                if side == "long"
                else di_minus[candidate] > di_plus[candidate]
            )
            if adx[candidate] >= min_peak and (aligned or not require_alignment):
                peak_index = candidate
                break
        peak_indices.append(peak_index)
        bars_since.append(index - peak_index if peak_index >= 0 else -1)
        if peak_index < 0:
            allowed.append(False)
            reasons.append("no_recent_adx_peak")
            continue
        if index - peak_index > max_since:
            allowed.append(False)
            reasons.append("peak_too_old")
            continue
        if adx[index] < min_current:
            allowed.append(False)
            reasons.append("current_adx_too_low")
            continue
        opposite = (
            di_minus[index] > di_plus[index] + margin
            if side == "long"
            else di_plus[index] > di_minus[index] + margin
        )
        if block_flip and opposite:
            allowed.append(False)
            reasons.append("opposite_di_flip")
            continue
        allowed.append(True)
        reasons.append("")
    return tuple(allowed), {
        "blocked_reason": tuple(reasons),
        "adx_current": tuple(adx),
        "di_plus_current": tuple(di_plus),
        "di_minus_current": tuple(di_minus),
        "adx_peak_idx": tuple(peak_indices),
        "bars_since_adx_peak": tuple(bars_since),
    }


def _blocker(
    item: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    side: str,
    records: tuple[ContextConsumptionRecord, ...],
) -> ComponentMask:
    component_id = str(item.get("component_id", ""))
    instance_id = str(item.get("instance_id", component_id))
    length = len(frame.time_ms)
    trace: dict[str, tuple[object, ...]] = {}
    if component_id == "no_blockers":
        intrinsic = tuple(True for _ in range(length))
    elif component_id == "counter_candle_blocker":
        if len(frame.market_bars) != length:
            raise InvalidRequestError("market bars unavailable for counter candle blocker")
        intrinsic = tuple(
            bar.close >= bar.open if side == "long" else bar.close <= bar.open
            for bar in frame.market_bars
        )
    elif component_id == "rsi_lookback_extreme_blocker":
        intrinsic, trace = _rsi_blocker(item, frame, plan, side)
    elif component_id == "trend_strength_episode_blocker":
        intrinsic, trace = _trend_strength_blocker(item, frame, plan, side)
    else:
        raise InvalidRequestError("unsupported blocker component", component_id=component_id)
    gate = _gate_for(records, role="blocker", instance_id=instance_id, side=side)
    allowed = _apply_gate(intrinsic, gate)
    return ComponentMask(
        role="blockers",
        component_id=component_id,
        instance_id=instance_id,
        side=side,
        intrinsic_allowed=intrinsic,
        context_allowed=gate,
        allowed=allowed,
        trace=trace,
    )


def evaluate_direction_and_blockers(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    context_records: tuple[ContextConsumptionRecord, ...],
) -> tuple[SideDirectionBlockers, ...]:
    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    blocker_items = tuple(
        _mapping(item, f"raw_spec.components.blockers[{index}]")
        for index, item in enumerate(
            _sequence(components.get("blockers", []), "raw_spec.components.blockers")
        )
    )
    if not blocker_items:
        blocker_items = ({"component_id": "no_blockers", "instance_id": "no_blockers"},)
    outputs: list[SideDirectionBlockers] = []
    for side in _enabled_sides(raw_spec):
        direction = _direction(raw_spec, frame, plan, side)
        blockers = tuple(
            _blocker(item, frame, plan, side, context_records) for item in blocker_items
        )
        blockers_ok = tuple(
            all(mask.allowed[index] for mask in blockers) for index in range(len(frame.time_ms))
        )
        pre_setup = tuple(a and b for a, b in zip(direction.allowed, blockers_ok, strict=True))
        outputs.append(SideDirectionBlockers(side, direction, blockers, blockers_ok, pre_setup))
    return tuple(outputs)
