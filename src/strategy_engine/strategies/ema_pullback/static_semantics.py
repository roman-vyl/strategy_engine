"""Authoritative static (market-data-free) semantic validation for ema_pullback.

Composition only -- every allowlist/identity rule is imported from
`raw_spec_identity.py`, the dependency-neutral module the evaluator
modules themselves import from. This module never re-derives a rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.composite_spec import (
    composite_items,
    phase_rule_composites,
    require_no_internal_key_collision,
)
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    BLOCKER_SUPPORTED,
    DIRECTION_SUPPORTED,
    EXIT_DISTANCE_SUPPORTED,
    EXIT_PARTIAL_TAKE_SUPPORTED,
    EXIT_SIGNAL_SUPPORTED,
    RISK_SUPPORTED,
    SETUP_SUPPORTED,
    TRIGGER_SUPPORTED,
    require_partial_take_ladder,
    require_unique_instance_ids,
    resolve_blocker_identity,
    resolve_direction_component_id,
    resolve_enabled_sides,
    resolve_exit_rule_groups,
    resolve_risk_component_id,
    resolve_setup_identity,
    resolve_trigger_rule,
)

_EXIT_GROUPS = ("always_on", "aligned", "countertrend", "neutral")


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _sequence(value: object, path: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(value)


def check_ema_pullback_static_semantics(raw_spec: Mapping[str, Any]) -> None:
    resolve_enabled_sides(raw_spec)

    direction_component_id = resolve_direction_component_id(raw_spec)
    if direction_component_id not in DIRECTION_SUPPORTED:
        raise InvalidRequestError(
            "unsupported direction component", component_id=direction_component_id
        )

    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    blockers = _sequence(components.get("blockers", []), "components.blockers")
    blocker_identity_pairs: list[tuple[object, str]] = []
    for index, blocker_raw in enumerate(blockers):
        blocker = _mapping(blocker_raw, f"components.blockers[{index}]")
        component_id, _ = resolve_blocker_identity(blocker)
        if component_id not in BLOCKER_SUPPORTED:
            raise InvalidRequestError(
                "unsupported blocker component", component_id=component_id
            )
        blocker_identity_pairs.append(
            (blocker.get("instance_id"), f"components.blockers[{index}].instance_id")
        )
    require_unique_instance_ids("components.blockers", tuple(blocker_identity_pairs))

    trigger_rule = resolve_trigger_rule(raw_spec)
    trigger_component_id = str(trigger_rule.get("component_id", "reclaim_anchor"))
    if trigger_component_id not in TRIGGER_SUPPORTED:
        raise InvalidRequestError(
            "unsupported trigger component", component_id=trigger_component_id
        )

    risk_component_id = resolve_risk_component_id(raw_spec)
    if risk_component_id not in RISK_SUPPORTED:
        raise InvalidRequestError("unsupported risk component", component_id=risk_component_id)

    setups = _sequence(raw_spec.get("setups", []), "setups")
    setup_identity_pairs: list[tuple[object, str]] = []
    for index, setup_raw in enumerate(setups):
        setup = _mapping(setup_raw, f"setups[{index}]")
        component_id, _ = resolve_setup_identity(setup)
        if component_id not in SETUP_SUPPORTED:
            raise InvalidRequestError("unsupported setup component", component_id=component_id)
        setup_identity_pairs.append(
            (setup.get("instance_id"), f"setups[{index}].instance_id")
        )
    require_unique_instance_ids("setups", tuple(setup_identity_pairs))
    contexts = raw_spec.get("contexts") or {}
    context_refs = (
        frozenset(str(ref) for ref in contexts) if isinstance(contexts, Mapping) else None
    )
    _check_composite_setups(setups, context_refs)
    _check_composite_phase_conditions(raw_spec, context_refs)

    exit_rule_groups = resolve_exit_rule_groups(raw_spec)
    exit_identity_pairs: list[tuple[object, str]] = []
    for group in _EXIT_GROUPS:
        for index, rule in enumerate(exit_rule_groups[group]):
            component_id = str(rule.get("component_id", ""))
            if (
                component_id not in EXIT_SIGNAL_SUPPORTED
                and component_id not in EXIT_DISTANCE_SUPPORTED
                and component_id not in EXIT_PARTIAL_TAKE_SUPPORTED
            ):
                raise InvalidRequestError(
                    "unsupported exit component", component_id=component_id
                )
            path = f"trade_management.exit_policy.{group}.exits[{index}].instance_id"
            exit_identity_pairs.append((rule.get("instance_id"), path))
    require_unique_instance_ids("trade_management.exit_policy", tuple(exit_identity_pairs))
    require_partial_take_ladder(exit_rule_groups)


def _check_composite_setups(
    setups: tuple[object, ...], context_refs: frozenset[str] | None
) -> None:
    """Structural validation of every `composite_setup` (design D1, D12)."""

    items = tuple(_mapping(item, f"setups[{index}]") for index, item in enumerate(setups))
    composites = composite_items(items)
    if not composites:
        return
    for spec in composites:
        for child in spec.children:
            if child.predicate is not None:
                parse_predicate(
                    child.predicate,
                    f"setup[{spec.instance_id}].{child.child_id}.predicate",
                    context_refs=context_refs,
                )
    require_no_internal_key_collision(
        tuple(str(item.get("instance_id", "")) for item in items), composites
    )


def _check_composite_phase_conditions(
    raw_spec: Mapping[str, Any], context_refs: frozenset[str] | None
) -> None:
    """Structural validation of every `composite_phase_condition`
    (`composite-managed-phase-condition-v1` design D1, D10). Atomic phase
    rules are not validated here, exactly as before."""

    trade_management = raw_spec.get("trade_management")
    if not isinstance(trade_management, Mapping):
        return
    exit_management = trade_management.get("exit_management")
    if not isinstance(exit_management, Mapping):
        return
    rules = exit_management.get("phase_rules")
    for index, rule in enumerate(rules if isinstance(rules, (list, tuple)) else ()):
        condition = rule.get("condition") if isinstance(rule, Mapping) else None
        # A predicate is never a phase_rule condition by itself (design D1).
        if isinstance(condition, Mapping) and "kind" in condition:
            raise InvalidRequestError(
                "a predicate is not a phase_rule condition; "
                "use it as a composite_phase_condition child",
                path=f"phase_rules[{index}].condition",
            )
    for index, spec in phase_rule_composites(exit_management):
        for child in spec.children:
            if child.predicate is not None:
                parse_predicate(
                    child.predicate,
                    f"phase_rules[{index}].condition.{child.child_id}.predicate",
                    context_refs=context_refs,
                )
