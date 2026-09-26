"""BBB-compatible direction and blocker semantics for ema_pullback."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
    GateIdentity,
)
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    BLOCKER_SUPPORTED,
    DIRECTION_SUPPORTED,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_blocker_identity as _blocker_identity,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_direction_component_id as _direction_component_id,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_enabled_sides as _enabled_sides,
)

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


def _float_series(frame: FeatureFrameLike, output_id: str) -> tuple[float, ...]:
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


def _supported_direction_component_id(raw_spec: Mapping[str, Any]) -> str:
    component_id = _direction_component_id(raw_spec)
    if component_id not in DIRECTION_SUPPORTED:
        raise InvalidRequestError("unsupported direction component", component_id=component_id)
    return component_id


def _direction(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
) -> ComponentMask:
    component_id = _supported_direction_component_id(raw_spec)
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


def _rsi_blocker_column(item: Mapping[str, Any], plan: EmaPullbackFeaturePlan) -> str:
    """Plan label of the RSI series an RSI blocker reads (shared by compute
    and resolve)."""

    rsi_spec = _mapping(item.get("rsi"), "blocker.rsi")
    timeframe = str(rsi_spec.get("timeframe", "base"))
    period = int(rsi_spec.get("period", 14))
    output_id = plan.rsi_columns.get((timeframe, period))
    if output_id is None:
        raise InvalidRequestError("missing RSI mapping for blocker")
    return output_id


def _rsi_blocker_params(item: Mapping[str, Any], side: str) -> tuple[int, float]:
    """Effective `(lookback, threshold)` of an RSI blocker for `side` --
    only the threshold of the evaluated side is read (shared by compute and
    resolve)."""

    lookback = int(item.get("lookback", 20))
    if lookback <= 0:
        raise InvalidRequestError("blocker lookback must be positive")
    threshold = (
        float(item.get("long_block_above", 80.0))
        if side == "long"
        else float(item.get("short_block_below", 20.0))
    )
    return lookback, threshold


def _rsi_blocker(
    item: Mapping[str, Any], frame: FeatureFrameLike, plan: EmaPullbackFeaturePlan, side: str
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    output_id = _rsi_blocker_column(item, plan)
    values = _float_series(frame, output_id)
    lookback, threshold = _rsi_blocker_params(item, side)
    # Positional, vectorized replacement for the per-bar Python loop
    # (design.md Decision 1, direction-blockers-vectorization): the
    # explicit isfinite gate is required, not redundant with the
    # comparison, because +/-inf must never count as "extreme" even
    # though e.g. `inf > threshold` is True in numpy. rolling(lookback,
    # min_periods=1).max() reproduces the original's shortened window at
    # the start (extreme[max(0, i-lookback+1):i+1]) exactly.
    arr = np.asarray(values, dtype=float)
    finite = np.isfinite(arr)
    extreme_arr = finite & (arr > threshold) if side == "long" else finite & (arr < threshold)
    seen_arr = (
        pd.Series(extreme_arr).rolling(lookback, min_periods=1).max().to_numpy().astype(bool)
    )
    allowed = tuple((~seen_arr).tolist())
    seen = tuple(seen_arr.tolist())
    return allowed, {"rsi": tuple(values), "extreme_seen": seen}


def _trend_strength_columns(
    item: Mapping[str, Any], plan: EmaPullbackFeaturePlan
) -> tuple[Mapping[str, Any], dict[str, str]]:
    """`(trend_strength params, adx/di_plus/di_minus plan labels)` (shared by
    compute and resolve)."""

    params = _mapping(item.get("trend_strength"), "blocker.trend_strength")
    timeframe = str(params.get("timeframe", "base"))
    period = int(params.get("adx_period", 14))
    columns = plan.adx_dmi_columns.get((timeframe, period))
    if columns is None:
        raise InvalidRequestError("missing ADX/DMI mapping for blocker")
    return params, columns


def _trend_strength_params(
    params: Mapping[str, Any],
) -> tuple[float, int, int, float, bool, bool, float]:
    """Effective trend-strength thresholds, post-defaults (shared by compute
    and resolve)."""

    return (
        float(params.get("min_adx_peak", 25.0)),
        int(params.get("peak_lookback_bars", 60)),
        int(params.get("max_bars_since_peak", 30)),
        float(params.get("min_current_adx", 15.0)),
        bool(params.get("require_di_alignment_on_peak", True)),
        bool(params.get("block_on_opposite_di_flip", True)),
        float(params.get("opposite_di_margin", 0.0)),
    )


def _trend_strength_blocker(
    item: Mapping[str, Any], frame: FeatureFrameLike, plan: EmaPullbackFeaturePlan, side: str
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    params, columns = _trend_strength_columns(item, plan)
    adx = _float_series(frame, columns["adx"])
    di_plus = _float_series(frame, columns["di_plus"])
    di_minus = _float_series(frame, columns["di_minus"])
    (
        min_peak,
        peak_lookback,
        max_since,
        min_current,
        require_alignment,
        block_flip,
        margin,
    ) = _trend_strength_params(params)
    # Positional running-last-qualifying-index replacement for the nested
    # backward scan (design.md Decision 2, direction-blockers-vectorization).
    # np.maximum.accumulate over per-bar candidate positions (-1 where not
    # qualifying) gives, at each i, the largest index <= i where a candidate
    # qualified -- exactly "most recent qualifying bar found scanning
    # backward", checked against the trailing peak_lookback window. The
    # elif-chain below is applied in the SAME priority order as the
    # original (indicator_not_ready > no_recent_adx_peak > peak_too_old >
    # current_adx_too_low > opposite_di_flip > allowed) via sequential
    # np.where overrides -- reordering these would change which reason
    # wins when multiple conditions hold on the same bar.
    adx_arr = np.asarray(adx, dtype=float)
    plus_arr = np.asarray(di_plus, dtype=float)
    minus_arr = np.asarray(di_minus, dtype=float)
    n = len(adx_arr)
    finite = np.isfinite(adx_arr) & np.isfinite(plus_arr) & np.isfinite(minus_arr)
    aligned = (plus_arr > minus_arr) if side == "long" else (minus_arr > plus_arr)
    qualifies = finite & (adx_arr >= min_peak) & (aligned | (not require_alignment))

    idx = np.arange(n)
    candidate_idx = np.where(qualifies, idx, -1)
    running_last_true = np.maximum.accumulate(candidate_idx)
    window_start = idx - peak_lookback + 1
    peak_index_arr = np.where(running_last_true >= window_start, running_last_true, -1)

    current_not_ready = ~finite
    peak_missing = peak_index_arr < 0
    bars_since_arr = np.where(peak_index_arr >= 0, idx - peak_index_arr, -1)
    peak_too_old = (~peak_missing) & (bars_since_arr > max_since)
    current_too_low = adx_arr < min_current
    opposite = (
        minus_arr > plus_arr + margin if side == "long" else plus_arr > minus_arr + margin
    )
    opposite_flip = block_flip & opposite

    allowed_arr = np.ones(n, dtype=bool)
    reasons_arr = np.full(n, "", dtype=object)

    allowed_arr &= ~current_not_ready
    reasons_arr = np.where(current_not_ready, "indicator_not_ready", reasons_arr)

    mask = (~current_not_ready) & peak_missing
    allowed_arr &= ~mask
    reasons_arr = np.where(mask, "no_recent_adx_peak", reasons_arr)

    mask = (~current_not_ready) & (~peak_missing) & peak_too_old
    allowed_arr &= ~mask
    reasons_arr = np.where(mask, "peak_too_old", reasons_arr)

    mask = (~current_not_ready) & (~peak_missing) & (~peak_too_old) & current_too_low
    allowed_arr &= ~mask
    reasons_arr = np.where(mask, "current_adx_too_low", reasons_arr)

    mask = (
        (~current_not_ready)
        & (~peak_missing)
        & (~peak_too_old)
        & (~current_too_low)
        & opposite_flip
    )
    allowed_arr &= ~mask
    reasons_arr = np.where(mask, "opposite_di_flip", reasons_arr)

    # A not-ready current bar forces peak_index/bars_since to -1
    # unconditionally, matching the original's early-continue that skips
    # peak search entirely for that bar.
    peak_index_out = np.where(current_not_ready, -1, peak_index_arr)
    bars_since_out = np.where(current_not_ready, -1, bars_since_arr)

    allowed = tuple(allowed_arr.tolist())
    reasons = tuple(str(value) for value in reasons_arr.tolist())
    peak_indices = tuple(int(value) for value in peak_index_out.tolist())
    bars_since = tuple(int(value) for value in bars_since_out.tolist())
    return allowed, {
        "blocked_reason": reasons,
        "adx_current": tuple(adx),
        "di_plus_current": tuple(di_plus),
        "di_minus_current": tuple(di_minus),
        "adx_peak_idx": peak_indices,
        "bars_since_adx_peak": bars_since,
    }


def _blocker(
    item: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    records: tuple[ContextConsumptionRecord, ...],
) -> ComponentMask:
    component_id, instance_id = _blocker_identity(item)
    if component_id not in BLOCKER_SUPPORTED:
        raise InvalidRequestError("unsupported blocker component", component_id=component_id)
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
    else:
        intrinsic, trace = _trend_strength_blocker(item, frame, plan, side)
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


def _combine_blocker_masks(
    blocker_allowed: tuple[tuple[bool, ...], ...], length: int
) -> tuple[bool, ...]:
    # Vectorized replacement for
    # `all(mask.allowed[index] for mask in blockers) for index in range(length)`
    # (design.md Decision 3, direction-blockers-vectorization). The empty
    # branch is explicit rather than relying on np.logical_and.reduce's
    # behavior on a zero-length stacked array, to guarantee it matches
    # Python's `all([]) == True` even though evaluate_direction_and_blockers
    # never actually calls this with zero blockers today.
    if not blocker_allowed:
        return tuple([True] * length)
    stacked = np.array(blocker_allowed, dtype=bool)
    reduced = np.logical_and.reduce(stacked, axis=0, initial=True)
    return tuple(reduced.tolist())


def _blocker_items(raw_spec: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    blocker_items = tuple(
        _mapping(item, f"raw_spec.components.blockers[{index}]")
        for index, item in enumerate(
            _sequence(components.get("blockers", []), "raw_spec.components.blockers")
        )
    )
    if not blocker_items:
        blocker_items = ({"component_id": "no_blockers", "instance_id": "no_blockers"},)
    return blocker_items


def evaluate_direction_and_blockers(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    context_records: tuple[ContextConsumptionRecord, ...],
) -> tuple[SideDirectionBlockers, ...]:
    blocker_items = _blocker_items(raw_spec)
    outputs: list[SideDirectionBlockers] = []
    for side in _enabled_sides(raw_spec):
        direction = _direction(raw_spec, frame, plan, side)
        blockers = tuple(
            _blocker(item, frame, plan, side, context_records) for item in blocker_items
        )
        blockers_ok = _combine_blocker_masks(
            tuple(mask.allowed for mask in blockers), len(frame.time_ms)
        )
        pre_setup = tuple(a and b for a, b in zip(direction.allowed, blockers_ok, strict=True))
        outputs.append(SideDirectionBlockers(side, direction, blockers, blockers_ok, pre_setup))
    return tuple(outputs)


# -- semantic node identity (batch-computation-reuse group 3) -----------------

DIRECTION_BLOCKER_NODE_VERSION = 1


def _feature_node(feature_ids: Mapping[str, NodeSpec], output_id: str) -> NodeSpec:
    """Identity of the series stored under a plan label (the lookup
    `_float_series` does against `frame.series`)."""

    try:
        return feature_ids[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc


def gate_node_for(
    gates: tuple[GateIdentity, ...], *, role: str, instance_id: str, side: str
) -> NodeSpec | None:
    """Identity counterpart of `_gate_for`: first gate whose labels match."""

    for gate in gates:
        if gate.role == role and gate.instance_id == instance_id and gate.side == side:
            return gate.node
    return None


def resolve_direction(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
) -> NodeSpec:
    """Identity of `_direction`'s allowed/trace output. Reads the side."""

    component_id = _supported_direction_component_id(raw_spec)
    return node_spec(
        f"direction.{component_id}",
        version=DIRECTION_BLOCKER_NODE_VERSION,
        upstream={
            role: _feature_node(feature_ids, plan.anchor_columns[role])
            for role in ("fast", "anchor", "slow")
        },
        side=side,
    )


def resolve_blocker_intrinsic(
    item: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
) -> NodeSpec:
    """Identity of one blocker's `intrinsic_allowed`/`trace` output.

    `no_blockers` is constant and side-free; every other blocker reads the
    side. `instance_id` is a label (it only selects the gate) and is not part
    of the intrinsic identity.
    """

    component_id, _instance_id = _blocker_identity(item)
    if component_id not in BLOCKER_SUPPORTED:
        raise InvalidRequestError("unsupported blocker component", component_id=component_id)
    kind = f"blocker.{component_id}"
    if component_id == "no_blockers":
        return node_spec(kind, version=DIRECTION_BLOCKER_NODE_VERSION)
    if component_id == "counter_candle_blocker":
        return node_spec(kind, version=DIRECTION_BLOCKER_NODE_VERSION, side=side)
    if component_id == "rsi_lookback_extreme_blocker":
        rsi = _feature_node(feature_ids, _rsi_blocker_column(item, plan))
        lookback, threshold = _rsi_blocker_params(item, side)
        return node_spec(
            kind,
            version=DIRECTION_BLOCKER_NODE_VERSION,
            params={"lookback": lookback, "threshold": threshold},
            upstream={"rsi": rsi},
            side=side,
        )
    params, columns = _trend_strength_columns(item, plan)
    upstream = {role: _feature_node(feature_ids, columns[role]) for role in columns}
    (
        min_peak,
        peak_lookback,
        max_since,
        min_current,
        require_alignment,
        block_flip,
        margin,
    ) = _trend_strength_params(params)
    return node_spec(
        kind,
        version=DIRECTION_BLOCKER_NODE_VERSION,
        params={
            "min_adx_peak": min_peak,
            "peak_lookback_bars": peak_lookback,
            "max_bars_since_peak": max_since,
            "min_current_adx": min_current,
            "require_di_alignment_on_peak": require_alignment,
            "block_on_opposite_di_flip": block_flip,
            "opposite_di_margin": margin,
        },
        upstream=upstream,
        side=side,
    )


def gated_mask_node(intrinsic: NodeSpec, gate: NodeSpec | None) -> NodeSpec:
    """Identity of `_apply_gate(intrinsic, gate)`: the gated mask alone
    (without the intrinsic node's trace). An absent gate is an explicit
    `None` upstream, so every kind keeps one well-defined output shape."""

    return node_spec(
        "mask.gated",
        version=DIRECTION_BLOCKER_NODE_VERSION,
        upstream={"mask": intrinsic, "gate": gate},
    )


def and_masks_node(kind: str, masks: tuple[NodeSpec, ...]) -> NodeSpec:
    """Identity of an element-wise AND over masks (`np.logical_and.reduce`
    with `initial=True`): commutative and idempotent, so the upstream is an
    order/duplicate-insensitive set; an empty set is the all-True mask."""

    return node_spec(kind, version=DIRECTION_BLOCKER_NODE_VERSION, upstream={"masks": masks})


def pairwise_and_node(kind: str, left: NodeSpec, right: NodeSpec) -> NodeSpec:
    """Identity of `left AND right` for two bar-aligned masks."""

    return and_masks_node(kind, (left, right))


@dataclass(frozen=True, slots=True)
class SideDirectionBlockerIdentity:
    side: str
    direction: NodeSpec
    blocker_intrinsic: tuple[tuple[str, NodeSpec], ...]
    blocker_allowed: tuple[tuple[str, NodeSpec], ...]
    blockers_ok: NodeSpec
    pre_setup_allowed: NodeSpec


def resolve_direction_and_blockers(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    gates: tuple[GateIdentity, ...],
) -> tuple[SideDirectionBlockerIdentity, ...]:
    """Identity twin of `evaluate_direction_and_blockers` (per enabled side,
    same order). Blocker entries are keyed by the instance_id label only for
    attribution; the identities themselves never include it."""

    blocker_items = _blocker_items(raw_spec)
    outputs: list[SideDirectionBlockerIdentity] = []
    for side in _enabled_sides(raw_spec):
        direction = resolve_direction(raw_spec, plan, feature_ids, side)
        intrinsic: list[tuple[str, NodeSpec]] = []
        allowed: list[tuple[str, NodeSpec]] = []
        for item in blocker_items:
            _component_id, instance_id = _blocker_identity(item)
            node = resolve_blocker_intrinsic(item, plan, feature_ids, side)
            gate = gate_node_for(gates, role="blocker", instance_id=instance_id, side=side)
            intrinsic.append((instance_id, node))
            allowed.append((instance_id, gated_mask_node(node, gate)))
        blockers_ok = and_masks_node("mask.all", tuple(node for _, node in allowed))
        outputs.append(
            SideDirectionBlockerIdentity(
                side=side,
                direction=direction,
                blocker_intrinsic=tuple(intrinsic),
                blocker_allowed=tuple(allowed),
                blockers_ok=blockers_ok,
                pre_setup_allowed=pairwise_and_node("mask.all", direction, blockers_ok),
            )
        )
    return tuple(outputs)
