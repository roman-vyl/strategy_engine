"""Dependency-neutral pure `raw_spec` component/identity resolution.

No import from `feature_plan.py`, `exits.py`, `setups.py`,
`direction_blockers.py`, `triggers.py`, or `risk.py` -- every one of
those modules (plus `static_semantics.py`) imports *from* this module,
never the other way, keeping the family-level `component_id`
allowlists and `instance_id` requirements defined exactly once.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from math import isfinite
from typing import Any, Literal

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
EXIT_PARTIAL_TAKE_SUPPORTED = frozenset({"pct_partial_take", "atr_partial_take"})
INITIAL_R_STOP_SUPPORTED = frozenset({"initial_r_lock_stop", "initial_r_trailing_stop"})
InitialRStopFormula = Literal["initial_r_lock", "initial_r_trailing"]
PARTIAL_TAKE_EXIT_KIND = "partial_take"
BLOCKER_SUPPORTED = frozenset(
    {
        "no_blockers",
        "counter_candle_blocker",
        "rsi_lookback_extreme_blocker",
        "trend_strength_episode_blocker",
    }
)
SETUP_SUPPORTED = frozenset(
    {
        "untouched_anchor_setup",
        "ema_bounce_counter_setup",
        "anchor_stack_width_setup",
        "composite_setup",
    }
)
DIRECTION_SUPPORTED = frozenset({"ema_anchor_stack_trend"})


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


def _positive_finite(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidRequestError(f"{path} must be a positive number")
    try:
        number = float(value)
    except ValueError as exc:
        raise InvalidRequestError(f"{path} must be a positive number") from exc
    if not isfinite(number) or number <= 0:
        raise InvalidRequestError(f"{path} must be a positive number")
    return number


def _non_negative_finite(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidRequestError(f"{path} must be a non-negative number")
    try:
        number = float(value)
    except ValueError as exc:
        raise InvalidRequestError(f"{path} must be a non-negative number") from exc
    if not isfinite(number) or number < 0:
        raise InvalidRequestError(f"{path} must be a non-negative number")
    return number


def resolve_initial_r_stop(
    component_id: str, params: Mapping[str, Any], path: str
) -> tuple[InitialRStopFormula, float, float] | None:
    """Closed execution formula, trigger R and action distance R of one
    initial-R managed stop (OpenSpec `initial-r-stop-management-v1` D1), or
    `None` for any other stop component. Bounds keep the first eligible
    candidate at or beyond entry: `0 <= lock_r <= trigger_r` and
    `0 < trail_distance_r <= trigger_r`."""

    if component_id not in INITIAL_R_STOP_SUPPORTED:
        return None
    trigger_r = _positive_finite(params.get("trigger_r"), f"{path}.trigger_r")
    if component_id == "initial_r_lock_stop":
        lock_r = _non_negative_finite(params.get("lock_r"), f"{path}.lock_r")
        if lock_r > trigger_r:
            raise InvalidRequestError(f"{path}.lock_r must not exceed trigger_r")
        return "initial_r_lock", trigger_r, lock_r
    trail_r = _positive_finite(params.get("trail_distance_r"), f"{path}.trail_distance_r")
    if trail_r > trigger_r:
        raise InvalidRequestError(f"{path}.trail_distance_r must not exceed trigger_r")
    return "initial_r_trailing", trigger_r, trail_r


def require_initial_r_stops(raw_spec: Mapping[str, Any]) -> None:
    """Static parameter check of every initial-R managed stop. Other stop
    management components are not validated here, exactly as before."""

    trade_management = raw_spec.get("trade_management")
    if not isinstance(trade_management, Mapping):
        return
    exit_management = trade_management.get("exit_management")
    if not isinstance(exit_management, Mapping):
        return
    stops = exit_management.get("stop_management")
    for index, stop in enumerate(stops if isinstance(stops, (list, tuple)) else ()):
        if not isinstance(stop, Mapping):
            continue
        component_id = str(stop.get("component_id", ""))
        if component_id not in INITIAL_R_STOP_SUPPORTED:
            continue
        path = f"trade_management.exit_management.stop_management[{index}].params"
        resolve_initial_r_stop(component_id, _mapping(stop.get("params", {}), path), path)


def resolve_partial_take_fraction(rule: Mapping[str, Any], path: str) -> float:
    """`fraction_of_initial` of one partial take rule, strictly in (0, 1)."""

    fraction = _positive_finite(rule.get("fraction_of_initial"), f"{path}.fraction_of_initial")
    if fraction >= 1:
        raise InvalidRequestError(f"{path}.fraction_of_initial must be below 1")
    return fraction


def resolve_partial_take_pct(rule: Mapping[str, Any], path: str) -> float:
    return _positive_finite(rule.get("pct"), f"{path}.pct")


def require_partial_take_ladder(
    groups: Mapping[str, tuple[Mapping[str, Any], ...]],
) -> None:
    """Static frozen partial take ladder rules (OpenSpec
    `frozen-partial-take-ladder-v1`, design D3/D5): exit kind bound to the
    family, `fraction_of_initial` in (0, 1), positive `pct`/`multiplier`,
    and per profile (always_on + profile) a fraction sum below 1 and a final
    `take_profit` in force. Leg levels are never compared with the final."""

    fractions: dict[str, Decimal] = {}
    takes: dict[str, bool] = {}
    for group in ("always_on", *_PROFILE_ORDER):
        total = Decimal(0)
        has_take = False
        for index, rule in enumerate(groups[group]):
            path = f"trade_management.exit_policy.{group}.exits[{index}]"
            component_id = str(rule.get("component_id", ""))
            exit_kind = str(rule.get("exit_kind", "signal"))
            if exit_kind == "take_profit":
                has_take = True
            if component_id not in EXIT_PARTIAL_TAKE_SUPPORTED:
                if exit_kind == PARTIAL_TAKE_EXIT_KIND:
                    raise InvalidRequestError(
                        "exit component has mismatched exit_kind",
                        component_id=component_id,
                        exit_kind=exit_kind,
                    )
                continue
            if exit_kind != PARTIAL_TAKE_EXIT_KIND:
                raise InvalidRequestError(
                    "partial take exit component requires exit_kind partial_take",
                    component_id=component_id,
                    exit_kind=exit_kind,
                )
            # Exact decimal sum of the shortest float reprs: 0.1 + 0.2 + 0.7 == 1.
            total += Decimal(repr(resolve_partial_take_fraction(rule, path)))
            if component_id == "pct_partial_take":
                resolve_partial_take_pct(rule, path)
            else:
                distance = _mapping(rule.get("distance"), f"{path}.distance")
                _positive_finite(distance.get("multiplier"), f"{path}.distance.multiplier")
        fractions[group] = total
        takes[group] = has_take
    for profile in _PROFILE_ORDER:
        total = fractions["always_on"] + fractions[profile]
        if total == 0:
            continue
        if total >= 1:
            raise InvalidRequestError(
                "partial take fractions must sum below 1 per profile", profile=profile
            )
        if not (takes["always_on"] or takes[profile]):
            raise InvalidRequestError(
                "partial takes require a take_profit rule in the same profile",
                profile=profile,
            )
