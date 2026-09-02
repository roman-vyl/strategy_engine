"""Authoritative static (market-data-free) semantic validation for ema_pullback.

Composition only -- every allowlist/identity rule is imported from
`raw_spec_identity.py`, the dependency-neutral module the evaluator
modules themselves import from. This module never re-derives a rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    BLOCKER_SUPPORTED,
    EXIT_DISTANCE_SUPPORTED,
    EXIT_SIGNAL_SUPPORTED,
    RISK_SUPPORTED,
    SETUP_SUPPORTED,
    TRIGGER_SUPPORTED,
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
    if direction_component_id != "ema_anchor_stack_trend":
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

    exit_rule_groups = resolve_exit_rule_groups(raw_spec)
    exit_identity_pairs: list[tuple[object, str]] = []
    for group in _EXIT_GROUPS:
        for index, rule in enumerate(exit_rule_groups[group]):
            component_id = str(rule.get("component_id", ""))
            if (
                component_id not in EXIT_SIGNAL_SUPPORTED
                and component_id not in EXIT_DISTANCE_SUPPORTED
            ):
                raise InvalidRequestError(
                    "unsupported exit component", component_id=component_id
                )
            path = f"trade_management.exit_policy.{group}.exits[{index}].instance_id"
            exit_identity_pairs.append((rule.get("instance_id"), path))
    require_unique_instance_ids("trade_management.exit_policy", tuple(exit_identity_pairs))
