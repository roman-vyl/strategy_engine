"""BBB-compatible side-aware context consumption policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.contexts import ContextBundle

HTF_REGIME_GATE_POLICY = "htf_regime_gate"
EXIT_PROFILE_BY_HTF_STATE_POLICY = "exit_profile_by_htf_state"
_VALID_REGIMES = frozenset({"aligned", "countertrend", "neutral"})


def resolve_htf_regime(raw_state: str, side: str) -> str:
    if raw_state not in {"up", "down", "neutral"}:
        return "neutral"
    if side == "long":
        return (
            "aligned" if raw_state == "up" else "countertrend" if raw_state == "down" else "neutral"
        )
    if side == "short":
        return (
            "aligned" if raw_state == "down" else "countertrend" if raw_state == "up" else "neutral"
        )
    raise InvalidRequestError("trade side must be long or short", side=side)


@dataclass(frozen=True, slots=True)
class ContextConsumptionRecord:
    role: str
    context_ref: str
    policy_id: str
    side: str | None
    component_id: str | None
    instance_id: str | None
    raw_state: tuple[str, ...]
    resolved_regime: tuple[str, ...] | None = None
    allowed: tuple[bool, ...] | None = None
    allowed_regimes: tuple[str, ...] = ()
    profile_long: tuple[str, ...] | None = None
    profile_short: tuple[str, ...] | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "role": self.role,
            "context_ref": self.context_ref,
            "policy_id": self.policy_id,
            "side": self.side,
            "component_id": self.component_id,
            "instance_id": self.instance_id,
            "raw_state": list(self.raw_state),
            "resolved_regime": list(self.resolved_regime)
            if self.resolved_regime is not None
            else None,
            "allowed": list(self.allowed) if self.allowed is not None else None,
            "allowed_regimes": list(self.allowed_regimes),
            "profile_long": list(self.profile_long) if self.profile_long is not None else None,
            "profile_short": list(self.profile_short) if self.profile_short is not None else None,
        }


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _enabled_sides(raw_spec: Mapping[str, Any]) -> tuple[str, ...]:
    raw = raw_spec.get("trade_sides", ["long"])
    if isinstance(raw, Mapping):
        raw = raw.get("enabled", ["long"])
    if not isinstance(raw, (list, tuple)):
        raise InvalidRequestError("raw_spec.trade_sides must be a list")
    sides = tuple(str(item) for item in raw)
    if any(side not in {"long", "short"} for side in sides):
        raise InvalidRequestError("raw_spec.trade_sides has invalid value")
    return sides


def _consumption(value: object, path: str) -> tuple[str, str, dict[str, Any]] | None:
    if value is None:
        return None
    item = _mapping(value, path)
    context_ref = str(item.get("context_ref", "")).strip()
    policy = _mapping(item.get("policy"), f"{path}.policy")
    policy_id = str(policy.get("policy_id", "")).strip()
    params = dict(_mapping(policy.get("params", {}), f"{path}.policy.params"))
    if not context_ref or not policy_id:
        raise InvalidRequestError(f"{path} requires context_ref and policy.policy_id")
    return context_ref, policy_id, params


def _raw_state(bundle: ContextBundle, context_ref: str) -> tuple[str, ...]:
    for output in bundle.outputs:
        if output.context_ref == context_ref:
            return output.state
    raise InvalidRequestError("unknown context_ref", context_ref=context_ref)


def _gate_record(
    *,
    role: str,
    component: Mapping[str, Any],
    consumption: tuple[str, str, dict[str, Any]],
    side: str,
    bundle: ContextBundle,
) -> ContextConsumptionRecord:
    context_ref, policy_id, params = consumption
    if policy_id != HTF_REGIME_GATE_POLICY:
        raise InvalidRequestError("unsupported context consumption policy", policy_id=policy_id)
    raw_allowed = params.get("allowed_regimes")
    if not isinstance(raw_allowed, list) or not raw_allowed:
        raise InvalidRequestError("allowed_regimes must be a non-empty list")
    allowed_regimes = tuple(str(item) for item in raw_allowed)
    if set(allowed_regimes) - _VALID_REGIMES:
        raise InvalidRequestError("allowed_regimes contains invalid values")
    raw = _raw_state(bundle, context_ref)
    resolved = tuple(resolve_htf_regime(item, side) for item in raw)
    return ContextConsumptionRecord(
        role=role,
        context_ref=context_ref,
        policy_id=policy_id,
        side=side,
        component_id=str(component.get("component_id"))
        if component.get("component_id") is not None
        else None,
        instance_id=str(component.get("instance_id"))
        if component.get("instance_id") is not None
        else None,
        raw_state=raw,
        resolved_regime=resolved,
        allowed=tuple(item in allowed_regimes for item in resolved),
        allowed_regimes=allowed_regimes,
    )


def build_context_consumption_evidence(
    raw_spec: Mapping[str, Any], bundle: ContextBundle
) -> tuple[ContextConsumptionRecord, ...]:
    records: list[ContextConsumptionRecord] = []
    sides = _enabled_sides(raw_spec)
    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    for role, raw_items in (
        ("blocker", components.get("blockers", [])),
        ("setup", raw_spec.get("setups", [])),
    ):
        if not isinstance(raw_items, list):
            raise InvalidRequestError(f"raw_spec {role} list must be an array")
        for index, raw_item in enumerate(raw_items):
            item = _mapping(raw_item, f"raw_spec.{role}[{index}]")
            consumption = _consumption(
                item.get("context_consumption"), f"raw_spec.{role}[{index}].context_consumption"
            )
            if consumption is None:
                continue
            for side in sides:
                records.append(
                    _gate_record(
                        role=role, component=item, consumption=consumption, side=side, bundle=bundle
                    )
                )

    trade_management = _mapping(raw_spec.get("trade_management", {}), "raw_spec.trade_management")
    exit_policy = _mapping(
        trade_management.get("exit_policy", {}), "raw_spec.trade_management.exit_policy"
    )
    exit_consumption = _consumption(
        exit_policy.get("context_consumption"),
        "raw_spec.trade_management.exit_policy.context_consumption",
    )
    if exit_consumption is not None:
        context_ref, policy_id, _params = exit_consumption
        if policy_id != EXIT_PROFILE_BY_HTF_STATE_POLICY:
            raise InvalidRequestError("unsupported exit context policy", policy_id=policy_id)
        raw = _raw_state(bundle, context_ref)
        long_profile = (
            tuple(resolve_htf_regime(item, "long") for item in raw)
            if "long" in sides
            else tuple("neutral" for _ in raw)
        )
        short_profile = (
            tuple(resolve_htf_regime(item, "short") for item in raw)
            if "short" in sides
            else tuple("neutral" for _ in raw)
        )
        records.append(
            ContextConsumptionRecord(
                role="exit_policy",
                context_ref=context_ref,
                policy_id=policy_id,
                side=None,
                component_id="exit_policy",
                instance_id=None,
                raw_state=raw,
                profile_long=long_profile,
                profile_short=short_profile,
            )
        )
    return tuple(records)
