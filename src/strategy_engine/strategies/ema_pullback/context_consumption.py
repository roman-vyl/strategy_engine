"""BBB-compatible side-aware context consumption policies."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
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


def _gate_allowed_regimes(policy_id: str, params: Mapping[str, Any]) -> tuple[str, ...]:
    """Validated `allowed_regimes` of one gate policy, in declared order
    (shared by `_gate_record` and `resolve_context_consumption`)."""

    if policy_id != HTF_REGIME_GATE_POLICY:
        raise InvalidRequestError("unsupported context consumption policy", policy_id=policy_id)
    raw_allowed = params.get("allowed_regimes")
    if not isinstance(raw_allowed, list) or not raw_allowed:
        raise InvalidRequestError("allowed_regimes must be a non-empty list")
    allowed_regimes = tuple(str(item) for item in raw_allowed)
    if set(allowed_regimes) - _VALID_REGIMES:
        raise InvalidRequestError("allowed_regimes contains invalid values")
    return allowed_regimes


def _gate_record(
    *,
    role: str,
    component: Mapping[str, Any],
    consumption: tuple[str, str, dict[str, Any]],
    side: str,
    bundle: ContextBundle,
) -> ContextConsumptionRecord:
    context_ref, policy_id, params = consumption
    allowed_regimes = _gate_allowed_regimes(policy_id, params)
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


def _gate_declarations(
    raw_spec: Mapping[str, Any], sides: tuple[str, ...]
) -> Iterator[tuple[str, Mapping[str, Any], tuple[str, str, dict[str, Any]], str]]:
    """`(role, component, consumption, side)` for every declared gate, lazily
    in evaluation order (blockers, then setups; sides innermost) -- the
    single iteration shared by compute and `resolve_context_consumption`."""

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
                yield role, item, consumption, side


def _exit_consumption(raw_spec: Mapping[str, Any]) -> tuple[str, str] | None:
    """Validated `(context_ref, policy_id)` of the exit-profile consumption,
    if declared (shared by compute and `resolve_exit_profiles`)."""

    trade_management = _mapping(raw_spec.get("trade_management", {}), "raw_spec.trade_management")
    exit_policy = _mapping(
        trade_management.get("exit_policy", {}), "raw_spec.trade_management.exit_policy"
    )
    exit_consumption = _consumption(
        exit_policy.get("context_consumption"),
        "raw_spec.trade_management.exit_policy.context_consumption",
    )
    if exit_consumption is None:
        return None
    context_ref, policy_id, _params = exit_consumption
    if policy_id != EXIT_PROFILE_BY_HTF_STATE_POLICY:
        raise InvalidRequestError("unsupported exit context policy", policy_id=policy_id)
    return context_ref, policy_id


def build_context_consumption_evidence(
    raw_spec: Mapping[str, Any], bundle: ContextBundle
) -> tuple[ContextConsumptionRecord, ...]:
    records: list[ContextConsumptionRecord] = []
    sides = _enabled_sides(raw_spec)
    for role, item, consumption, side in _gate_declarations(raw_spec, sides):
        records.append(
            _gate_record(
                role=role, component=item, consumption=consumption, side=side, bundle=bundle
            )
        )

    exit_consumption = _exit_consumption(raw_spec)
    if exit_consumption is not None:
        context_ref, policy_id = exit_consumption
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


# -- semantic node identity (batch-computation-reuse group 3) -----------------

CONTEXT_CONSUMPTION_NODE_VERSION = 1


@dataclass(frozen=True, slots=True)
class GateIdentity:
    """Identity of one gate record's `resolved_regime`/`allowed` output, with
    the labels `_gate_for` lookups match on (role/instance_id/side exactly as
    the compute-side record carries them)."""

    role: str
    instance_id: str | None
    side: str
    node: NodeSpec


def _context_node(context_ids: Mapping[str, NodeSpec], context_ref: str) -> NodeSpec:
    node = context_ids.get(context_ref)
    if node is None:
        raise InvalidRequestError("unknown context_ref", context_ref=context_ref)
    return node


def resolve_context_consumption(
    raw_spec: Mapping[str, Any], context_ids: Mapping[str, NodeSpec]
) -> tuple[GateIdentity, ...]:
    """Gate identities, in the same order compute emits gate records.

    A gate reads the context's raw state and the side; `allowed_regimes` is
    only used for membership, so its identity is the de-duplicated, sorted
    set (declared order and repeats are labels on the echoed record only).
    """

    sides = _enabled_sides(raw_spec)
    gates: list[GateIdentity] = []
    for role, item, consumption, side in _gate_declarations(raw_spec, sides):
        context_ref, policy_id, params = consumption
        allowed_regimes = _gate_allowed_regimes(policy_id, params)
        gates.append(
            GateIdentity(
                role=role,
                instance_id=(
                    str(item.get("instance_id")) if item.get("instance_id") is not None else None
                ),
                side=side,
                node=node_spec(
                    "context_consumption.htf_regime_gate",
                    version=CONTEXT_CONSUMPTION_NODE_VERSION,
                    params={"allowed_regimes": frozenset(allowed_regimes)},
                    upstream={"context": _context_node(context_ids, context_ref)},
                    side=side,
                ),
            )
        )
    return tuple(gates)


def constant_neutral_profile() -> NodeSpec:
    """The all-"neutral" profile series: used when no exit consumption is
    declared and for a side that is not enabled (identical computation)."""

    return node_spec(
        "context_consumption.exit_profile.constant_neutral",
        version=CONTEXT_CONSUMPTION_NODE_VERSION,
    )


def resolve_exit_profiles(
    raw_spec: Mapping[str, Any], context_ids: Mapping[str, NodeSpec]
) -> tuple[NodeSpec | None, NodeSpec, NodeSpec]:
    """`(context_state, profile_long, profile_short)` identities consumed by
    the exit policy. `context_state` is the context node itself (its raw
    state), or `None` when no exit consumption is declared (then the exit
    policy uses an all-"neutral" state)."""

    sides = _enabled_sides(raw_spec)
    exit_consumption = _exit_consumption(raw_spec)
    if exit_consumption is None:
        return None, constant_neutral_profile(), constant_neutral_profile()
    context = _context_node(context_ids, exit_consumption[0])

    def profile(side: str) -> NodeSpec:
        if side not in sides:
            return constant_neutral_profile()
        return node_spec(
            "context_consumption.exit_profile",
            version=CONTEXT_CONSUMPTION_NODE_VERSION,
            upstream={"context": context},
            side=side,
        )

    return context, profile("long"), profile("short")
