"""Dependency-neutral pure `raw_spec` component/identity resolution.

No import from `feature_plan.py`, `exits.py`, `setups.py`,
`direction_blockers.py`, `triggers.py`, or `risk.py` -- every one of
those modules (plus `static_semantics.py`) imports *from* this module,
never the other way, keeping the family-level `component_id`
allowlists and `instance_id` requirements defined exactly once.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError

_VALID_SIDES = frozenset({"long", "short"})
_PROFILE_ORDER = ("aligned", "countertrend", "neutral")

RISK_SUPPORTED = frozenset({"no_risk_filter"})
TRIGGER_SUPPORTED = frozenset({"reclaim_anchor", "strong_reclaim_anchor", "touch_anchor"})
EXIT_SIGNAL_SUPPORTED = frozenset(
    {"no_signal_exit", "rsi_signal_exit", "ema_close_loss_exit", "ema_cross_loss_exit"}
)
EXIT_DISTANCE_SUPPORTED = frozenset(
    {
        "atr_stop_loss",
        "atr_take_profit",
        "constant_usd_stop_loss",
        "constant_usd_take_profit",
    }
)
BLOCKER_SUPPORTED = frozenset(
    {
        "no_blockers",
        "counter_candle_blocker",
        "rsi_lookback_extreme_blocker",
        "trend_strength_episode_blocker",
    }
)
SETUP_SUPPORTED = frozenset(
    {"untouched_anchor_setup", "ema_bounce_counter_setup", "anchor_stack_width_setup"}
)


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _sequence(value: object, path: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(value)


def _list(value: object, path: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(_mapping(item, f"{path}[{index}]") for index, item in enumerate(value))


def resolve_enabled_sides(raw_spec: Mapping[str, Any]) -> tuple[str, ...]:
    """Moved verbatim from `direction_blockers.py::_enabled_sides`."""

    raw: object = raw_spec.get("trade_sides", ["long"])
    if isinstance(raw, Mapping):
        raw = raw.get("enabled", ["long"])
    sides = tuple(str(item) for item in _sequence(raw, "raw_spec.trade_sides"))
    if not sides or any(side not in _VALID_SIDES for side in sides):
        raise InvalidRequestError("raw_spec.trade_sides must contain long/short")
    return sides


def resolve_direction_component_id(raw_spec: Mapping[str, Any]) -> str:
    """Moved verbatim from `direction_blockers.py::_direction`'s inline check."""

    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    return str(components.get("direction", "ema_anchor_stack_trend"))


def resolve_blocker_identity(item: Mapping[str, Any]) -> tuple[str, str]:
    """Moved verbatim from `direction_blockers.py::_blocker`'s inline resolution."""

    component_id = str(item.get("component_id", ""))
    instance_id = str(item.get("instance_id", component_id))
    return component_id, instance_id


def resolve_trigger_rule(raw_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    """Moved verbatim from `triggers.py::_trigger_rule`."""

    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    raw = components.get("trigger", {"component_id": "reclaim_anchor", "lookback": 1})
    if isinstance(raw, str):
        return {"component_id": raw}
    return _mapping(raw, "raw_spec.components.trigger")


def resolve_risk_component_id(raw_spec: Mapping[str, Any]) -> str:
    """Moved verbatim from `risk.py::_risk_component_id`."""

    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    raw = components.get("risk", "no_risk_filter")
    if isinstance(raw, str):
        return raw
    payload = _mapping(raw, "raw_spec.components.risk")
    return str(payload.get("component_id", "no_risk_filter"))


def resolve_setup_identity(item: Mapping[str, Any]) -> tuple[str, str]:
    """Moved verbatim from `setups.py::_setup`'s inline resolution."""

    component_id = str(item.get("component_id", ""))
    instance_id = str(item.get("instance_id", component_id))
    return component_id, instance_id


def resolve_exit_rule_groups(
    raw_spec: Mapping[str, Any],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """Moved verbatim from `exits.py::_policy_rules`."""

    trade_management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    exit_policy = _mapping(trade_management.get("exit_policy", {}), "exit_policy")
    always = _mapping(exit_policy.get("always_on", {}), "exit_policy.always_on")
    profiles = _mapping(exit_policy.get("profiles", {}), "exit_policy.profiles")
    result = {"always_on": _list(always.get("exits", []), "always_on.exits")}
    for profile in _PROFILE_ORDER:
        payload = _mapping(profiles.get(profile, {}), f"exit_policy.profiles.{profile}")
        result[profile] = _list(payload.get("exits", []), f"profiles.{profile}.exits")
    return result


def require_non_empty_instance_id(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidRequestError(f"{path} must be a non-empty string")
    return value


def require_unique_instance_ids(scope: str, pairs: tuple[tuple[object, str], ...]) -> None:
    """Enforce old-BBB `spec.py::_validate_unique_instance_ids` parity.

    `pairs` is an ordered sequence of `(instance_id, path)`, where
    `instance_id` is the raw (unvalidated) value read off the rule.
    Raises on the first empty or duplicate `instance_id` encountered.
    """

    seen: set[str] = set()
    for raw_instance_id, path in pairs:
        instance_id = require_non_empty_instance_id(raw_instance_id, path)
        if instance_id in seen:
            raise InvalidRequestError(
                f"{scope} instance_id must be unique", instance_id=instance_id
            )
        seen.add(instance_id)
