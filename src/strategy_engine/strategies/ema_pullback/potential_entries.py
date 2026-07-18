"""Potential entry projection for EMA Pullback touch-anchor triggers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.exits import ExitPolicyEvaluation
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation


@dataclass(frozen=True, slots=True)
class PotentialEntry:
    side: str
    entry_price: tuple[float | None, ...]
    stop_price: tuple[float | None, ...]
    take_price: tuple[float | None, ...]


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _trigger_component(raw_spec: Mapping[str, Any]) -> str:
    components = _mapping(raw_spec.get("components", {}), "raw_spec.components")
    trigger = components.get("trigger", {"component_id": "reclaim_anchor"})
    if isinstance(trigger, str):
        return trigger
    return str(_mapping(trigger, "raw_spec.components.trigger").get("component_id", ""))


def _anchor_values(
    frame: FeatureFrame, plan: EmaPullbackFeaturePlan
) -> tuple[float | None, ...]:
    output_id = plan.anchor_columns["anchor"]
    try:
        values = frame.series[output_id]
    except KeyError as exc:
        raise InvalidRequestError(
            "missing planned anchor feature series", output_id=output_id
        ) from exc
    return tuple(None if value is None else float(value) for value in values)


def _distances_for(
    exit_policy: ExitPolicyEvaluation, side: str
) -> tuple[tuple[float | None, ...], tuple[float | None, ...]]:
    if side == "long":
        return exit_policy.stop_loss_distance_long, exit_policy.take_profit_distance_long
    if side == "short":
        return exit_policy.stop_loss_distance_short, exit_policy.take_profit_distance_short
    raise InvalidRequestError("trade side must be long or short", side=side)


def _project_side(
    setup: SideSetupEvaluation,
    anchors: tuple[float | None, ...],
    stop_distances: tuple[float | None, ...],
    take_distances: tuple[float | None, ...],
) -> PotentialEntry:
    length = len(anchors)
    if not all(
        len(values) == length
        for values in (setup.pre_trigger_allowed, stop_distances, take_distances)
    ):
        raise InvalidRequestError("potential entry inputs must share the bar axis")

    entries: list[float | None] = []
    stops: list[float | None] = []
    takes: list[float | None] = []
    for allowed, anchor, stop_distance, take_distance in zip(
        setup.pre_trigger_allowed,
        anchors,
        stop_distances,
        take_distances,
        strict=True,
    ):
        if (
            not allowed
            or anchor is None
            or stop_distance is None
            or take_distance is None
            or not all(
                isfinite(value) and value > 0
                for value in (anchor, stop_distance, take_distance)
            )
        ):
            entry = stop = take = None
        else:
            entry = anchor
            if setup.side == "long":
                stop = entry - stop_distance
                take = entry + take_distance
            else:
                stop = entry + stop_distance
                take = entry - take_distance
            if not all(isfinite(value) and value > 0 for value in (entry, stop, take)):
                entry = stop = take = None
        entries.append(entry)
        stops.append(stop)
        takes.append(take)
    return PotentialEntry(setup.side, tuple(entries), tuple(stops), tuple(takes))


def project_potential_entries(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    setups: tuple[SideSetupEvaluation, ...],
    exit_policy: ExitPolicyEvaluation,
) -> dict[str, PotentialEntry]:
    """Project enabled-side potential prices from already evaluated range data."""

    if _trigger_component(raw_spec) != "touch_anchor":
        return {}
    anchors = _anchor_values(frame, plan)
    output: dict[str, PotentialEntry] = {}
    for setup in setups:
        stop_distances, take_distances = _distances_for(exit_policy, setup.side)
        output[setup.side] = _project_side(
            setup, anchors, stop_distances, take_distances
        )
    return output


def potential_entries_to_wire(
    entries: Mapping[str, PotentialEntry],
) -> dict[str, object]:
    def decimal_or_none(value: float | None) -> str | None:
        if value is None or not isfinite(value):
            return None
        return normalized_decimal_text(Decimal(str(value)))

    return {
        side: {
            "entry_price": [decimal_or_none(value) for value in item.entry_price],
            "stop_price": [decimal_or_none(value) for value in item.stop_price],
            "take_price": [decimal_or_none(value) for value in item.take_price],
        }
        for side, item in entries.items()
    }
