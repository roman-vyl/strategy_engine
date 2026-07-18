"""Potential entry projection for EMA Pullback touch-anchor triggers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.exits import ExitPolicyEvaluation
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation
from strategy_engine.strategies.ema_pullback.triggers import (
    SideTriggerEvaluation,
    touch_anchor_close_ok,
)


@dataclass(frozen=True, slots=True)
class PotentialEntry:
    side: str
    entry_price: tuple[float | None, ...]
    stop_price: tuple[float | None, ...]
    take_price: tuple[float | None, ...]


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
    trigger_close_ok: tuple[bool, ...],
    anchors: tuple[float | None, ...],
    stop_distances: tuple[float | None, ...],
    take_distances: tuple[float | None, ...],
) -> PotentialEntry:
    length = len(anchors)
    if not all(
        len(values) == length
        for values in (
            setup.pre_trigger_allowed,
            trigger_close_ok,
            stop_distances,
            take_distances,
        )
    ):
        raise InvalidRequestError("potential entry inputs must share the bar axis")

    entries: list[float | None] = []
    stops: list[float | None] = []
    takes: list[float | None] = []
    for allowed, close_ok, anchor, stop_distance, take_distance in zip(
        setup.pre_trigger_allowed,
        trigger_close_ok,
        anchors,
        stop_distances,
        take_distances,
        strict=True,
    ):
        if (
            not allowed
            or not close_ok
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
            elif setup.side == "short":
                stop = entry + stop_distance
                take = entry - take_distance
            else:
                raise InvalidRequestError(
                    "trade side must be long or short", side=setup.side
                )
            if not all(isfinite(value) and value > 0 for value in (entry, stop, take)):
                entry = stop = take = None
        entries.append(entry)
        stops.append(stop)
        takes.append(take)
    return PotentialEntry(setup.side, tuple(entries), tuple(stops), tuple(takes))


def project_potential_entries(
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    setups: tuple[SideSetupEvaluation, ...],
    triggers: tuple[SideTriggerEvaluation, ...],
    exit_policy: ExitPolicyEvaluation,
) -> dict[str, PotentialEntry]:
    """Project enabled-side potential prices from already evaluated range data."""

    component_ids = {item.trigger.component_id for item in triggers}
    if len(component_ids) != 1:
        raise InvalidRequestError(
            "potential entry triggers must share one component",
            component_ids=sorted(component_ids),
        )
    if component_ids != {"touch_anchor"}:
        return {}

    trigger_by_side = {item.side: item for item in triggers}
    if len(trigger_by_side) != len(triggers):
        raise InvalidRequestError("potential entry triggers must have unique sides")

    anchors = _anchor_values(frame, plan)
    output: dict[str, PotentialEntry] = {}
    for setup in setups:
        trigger = trigger_by_side.get(setup.side)
        if trigger is None:
            raise InvalidRequestError(
                "missing trigger evaluation for potential entry side", side=setup.side
            )
        stop_distances, take_distances = _distances_for(exit_policy, setup.side)
        output[setup.side] = _project_side(
            setup,
            touch_anchor_close_ok(trigger),
            anchors,
            stop_distances,
            take_distances,
        )
    if set(trigger_by_side) != set(output):
        raise InvalidRequestError("setup and trigger sides must match")
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
