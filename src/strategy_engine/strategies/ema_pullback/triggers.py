"""BBB-compatible ema_pullback trigger semantics and composition."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.evaluation_context import EvaluationContext, compute_through
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.ema_pullback.direction_blockers import and_pair, pairwise_and_node
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    TRIGGER_SUPPORTED as _SUPPORTED,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_trigger_rule as _trigger_rule,
)
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation, SideSetupIdentity

_VALID_SIDES = frozenset({"long", "short"})


@dataclass(frozen=True, slots=True)
class TriggerMask:
    component_id: str
    side: str
    allowed: tuple[bool, ...]
    trace: dict[str, tuple[object, ...]]

    def to_wire(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "side": self.side,
            "allowed": list(self.allowed),
            "trace": {key: list(values) for key, values in self.trace.items()},
            "counters": {
                "triggered_count": sum(self.allowed),
                "not_triggered_count": len(self.allowed) - sum(self.allowed),
            },
        }


@dataclass(frozen=True, slots=True)
class SideTriggerEvaluation:
    side: str
    trigger: TriggerMask
    pre_risk_entry_allowed: tuple[bool, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "side": self.side,
            "trigger": self.trigger.to_wire(),
            "pre_risk_entry_allowed": list(self.pre_risk_entry_allowed),
        }


def touch_anchor_close_ok(evaluation: SideTriggerEvaluation) -> tuple[bool, ...]:
    """Return the typed close-side precondition from an evaluated touch trigger."""

    trigger = evaluation.trigger
    if trigger.component_id != "touch_anchor":
        raise InvalidRequestError(
            "potential entry trigger must be touch_anchor",
            component_id=trigger.component_id,
        )
    values = trigger.trace.get("close_ok")
    if (
        values is None
        or len(values) != len(trigger.allowed)
        or any(not isinstance(value, bool) for value in values)
    ):
        raise InvalidRequestError(
            "touch_anchor trigger must expose a bar-aligned boolean close_ok trace",
            side=evaluation.side,
        )
    return cast(tuple[bool, ...], values)


def _float_series(frame: FeatureFrameLike, output_id: str) -> tuple[float, ...]:
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc
    return tuple(float("nan") if value is None else float(value) for value in values)


def _market_values(frame: FeatureFrameLike, field: str) -> tuple[float, ...]:
    if len(frame.market_bars) != len(frame.time_ms):
        raise InvalidRequestError("market bars unavailable for trigger evaluation")
    return frame_market_arrays(frame).values(field)


def _rolling_reclaim(
    frame: FeatureFrameLike,
    anchor: tuple[float, ...],
    *,
    side: str,
    lookback: int,
    close_probe: bool,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    if lookback <= 0:
        raise InvalidRequestError("trigger.lookback must be > 0")
    close = _market_values(frame, "close")
    low = _market_values(frame, "low")
    high = _market_values(frame, "high")
    if side == "long":
        probed = tuple(
            close_value <= anchor_value if close_probe else low_value <= anchor_value
            for close_value, low_value, anchor_value in zip(close, low, anchor, strict=True)
        )
        reclaimed = tuple(
            close_value > anchor_value
            for close_value, anchor_value in zip(close, anchor, strict=True)
        )
    elif side == "short":
        probed = tuple(
            close_value >= anchor_value if close_probe else high_value >= anchor_value
            for close_value, high_value, anchor_value in zip(close, high, anchor, strict=True)
        )
        reclaimed = tuple(
            close_value < anchor_value
            for close_value, anchor_value in zip(close, anchor, strict=True)
        )
    else:
        raise InvalidRequestError("trade side must be long or short", side=side)
    had_prior_probe = tuple(
        any(probed[index - lookback : index]) if index >= lookback else False
        for index in range(len(probed))
    )
    trigger = tuple(
        prior and reclaim for prior, reclaim in zip(had_prior_probe, reclaimed, strict=True)
    )
    return trigger, {
        "close": close,
        "anchor": anchor,
        "probed": probed,
        "had_prior_probe": had_prior_probe,
        "reclaimed": reclaimed,
        "trigger": trigger,
    }


def _touch_anchor(
    frame: FeatureFrameLike,
    anchor: tuple[float, ...],
    *,
    side: str,
) -> tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]:
    close = _market_values(frame, "close")
    low = _market_values(frame, "low")
    high = _market_values(frame, "high")
    if side == "long":
        touch = tuple(
            low_value <= anchor_value for low_value, anchor_value in zip(low, anchor, strict=True)
        )
        close_ok = tuple(
            close_value >= anchor_value
            for close_value, anchor_value in zip(close, anchor, strict=True)
        )
    elif side == "short":
        touch = tuple(
            high_value >= anchor_value
            for high_value, anchor_value in zip(high, anchor, strict=True)
        )
        close_ok = tuple(
            close_value <= anchor_value
            for close_value, anchor_value in zip(close, anchor, strict=True)
        )
    else:
        raise InvalidRequestError("trade side must be long or short", side=side)
    trigger = tuple(left and right for left, right in zip(touch, close_ok, strict=True))
    return trigger, {"touch": touch, "close_ok": close_ok, "trigger": trigger}


def _trigger_component(raw_spec: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    """Validated `(trigger rule, component_id)`, post-defaults (shared by
    compute and resolve)."""

    rule = _trigger_rule(raw_spec)
    component_id = str(rule.get("component_id", "reclaim_anchor"))
    if component_id not in _SUPPORTED:
        raise InvalidRequestError("unsupported trigger component", component_id=component_id)
    return rule, component_id


def _reclaim_lookback(rule: Mapping[str, Any]) -> int:
    """Effective reclaim lookback, post-default (validated at use by
    `_rolling_reclaim`; shared by compute and resolve)."""

    return int(rule.get("lookback", 1))


def evaluate_triggers(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    setups: tuple[SideSetupEvaluation, ...],
    *,
    context: EvaluationContext | None = None,
    identities: tuple[SideTriggerIdentity, ...] | None = None,
) -> tuple[SideTriggerEvaluation, ...]:
    """`context` + `identities` (the `resolve_triggers` twin of this exact
    call; batch-computation-reuse 4.6): each side's trigger node and its
    pre-risk composition are computed through the context's memo at the
    point they are computed today. Without them, everything computes
    directly."""

    rule, component_id = _trigger_component(raw_spec)
    anchor = _float_series(frame, plan.anchor_columns["anchor"])
    if identities is not None and tuple(item.side for item in identities) != tuple(
        prior.side for prior in setups
    ):
        identities = None  # not this call's twin: never memoize on a mismatch
    outputs: list[SideTriggerEvaluation] = []
    for index, prior in enumerate(setups):
        if prior.side not in _VALID_SIDES:
            raise InvalidRequestError("trade side must be long or short", side=prior.side)
        ids = identities[index] if identities is not None else None
        compute: functools.partial[tuple[tuple[bool, ...], dict[str, tuple[object, ...]]]]
        if component_id == "touch_anchor":
            compute = functools.partial(_touch_anchor, frame, anchor, side=prior.side)
        else:
            lookback = _reclaim_lookback(rule)
            compute = functools.partial(
                _rolling_reclaim,
                frame,
                anchor,
                side=prior.side,
                lookback=lookback,
                close_probe=component_id == "strong_reclaim_anchor",
            )
        allowed, trace = compute_through(context, ids.trigger if ids else None, compute)
        pre_risk = compute_through(
            context,
            ids.pre_risk_entry_allowed if ids else None,
            functools.partial(and_pair, prior.pre_trigger_allowed, allowed),
        )
        outputs.append(
            SideTriggerEvaluation(
                side=prior.side,
                # A private trace dict per consumer: a memoized trace is
                # shared by every candidate that reads it.
                trigger=TriggerMask(component_id, prior.side, allowed, dict(trace)),
                pre_risk_entry_allowed=pre_risk,
            )
        )
    return tuple(outputs)


# -- semantic node identity (batch-computation-reuse group 3) -----------------

TRIGGER_NODE_VERSION = 1


@dataclass(frozen=True, slots=True)
class SideTriggerIdentity:
    side: str
    trigger: NodeSpec
    pre_risk_entry_allowed: NodeSpec


def resolve_trigger(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
) -> NodeSpec:
    """Identity of one side's trigger `allowed`/`trace`. Every trigger reads
    the side; `lookback` is part of the identity only for the reclaim
    variants that read it (touch_anchor ignores it)."""

    rule, component_id = _trigger_component(raw_spec)
    if side not in _VALID_SIDES:
        raise InvalidRequestError("trade side must be long or short", side=side)
    try:
        anchor = feature_ids[plan.anchor_columns["anchor"]]
    except KeyError as exc:
        raise InvalidRequestError(
            "missing planned feature series", output_id=plan.anchor_columns["anchor"]
        ) from exc
    params: dict[str, object] = {}
    if component_id != "touch_anchor":
        lookback = _reclaim_lookback(rule)
        if lookback <= 0:
            raise InvalidRequestError("trigger.lookback must be > 0")
        params["lookback"] = lookback
    return node_spec(
        f"trigger.{component_id}",
        version=TRIGGER_NODE_VERSION,
        params=params,
        upstream={"anchor": anchor},
        side=side,
    )


def resolve_triggers(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    setups: tuple[SideSetupIdentity, ...],
) -> tuple[SideTriggerIdentity, ...]:
    """Identity twin of `evaluate_triggers` (per side of `setups`)."""

    outputs: list[SideTriggerIdentity] = []
    for prior in setups:
        trigger = resolve_trigger(raw_spec, plan, feature_ids, prior.side)
        outputs.append(
            SideTriggerIdentity(
                side=prior.side,
                trigger=trigger,
                pre_risk_entry_allowed=pairwise_and_node(
                    "mask.all", prior.pre_trigger_allowed, trigger
                ),
            )
        )
    return tuple(outputs)
