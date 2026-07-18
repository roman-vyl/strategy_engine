"""BBB-compatible ema_pullback trigger semantics and composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation

_VALID_SIDES = frozenset({"long", "short"})
_SUPPORTED = frozenset({"reclaim_anchor", "strong_reclaim_anchor", "touch_anchor"})


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


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _float_series(frame: FeatureFrame, output_id: str) -> tuple[float, ...]:
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc
    return tuple(float("nan") if value is None else float(value) for value in values)


def _market_values(frame: FeatureFrame, field: str) -> tuple[float, ...]:
    if len(frame.market_bars) != len(frame.time_ms):
        raise InvalidRequestError("market bars unavailable for trigger evaluation")
    return tuple(float(getattr(bar, field)) for bar in frame.market_bars)


def _rolling_reclaim(
    frame: FeatureFrame,
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
    frame: FeatureFrame,
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


def _trigger_rule(raw_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    raw = components.get("trigger", {"component_id": "reclaim_anchor", "lookback": 1})
    if isinstance(raw, str):
        return {"component_id": raw}
    return _mapping(raw, "raw_spec.components.trigger")


def evaluate_triggers(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    setups: tuple[SideSetupEvaluation, ...],
) -> tuple[SideTriggerEvaluation, ...]:
    rule = _trigger_rule(raw_spec)
    component_id = str(rule.get("component_id", "reclaim_anchor"))
    if component_id not in _SUPPORTED:
        raise InvalidRequestError("unsupported trigger component", component_id=component_id)
    anchor = _float_series(frame, plan.anchor_columns["anchor"])
    outputs: list[SideTriggerEvaluation] = []
    for prior in setups:
        if prior.side not in _VALID_SIDES:
            raise InvalidRequestError("trade side must be long or short", side=prior.side)
        if component_id == "touch_anchor":
            allowed, trace = _touch_anchor(frame, anchor, side=prior.side)
        else:
            lookback = int(rule.get("lookback", 1))
            allowed, trace = _rolling_reclaim(
                frame,
                anchor,
                side=prior.side,
                lookback=lookback,
                close_probe=component_id == "strong_reclaim_anchor",
            )
        pre_risk = tuple(
            setup_allowed and trigger_allowed
            for setup_allowed, trigger_allowed in zip(
                prior.pre_trigger_allowed, allowed, strict=True
            )
        )
        outputs.append(
            SideTriggerEvaluation(
                side=prior.side,
                trigger=TriggerMask(component_id, prior.side, allowed, trace),
                pre_risk_entry_allowed=pre_risk,
            )
        )
    return tuple(outputs)
