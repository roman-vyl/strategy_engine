"""EMA Pullback live-entry projection adapter."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.application.load_live_feature_frame import LiveFeatureFrameBundle
from strategy_engine.strategies.contracts import (
    LIVE_ENTRY_MODES,
    LiveEntryMode,
    LiveEntryPlan,
    LiveEntryProjectionRequest,
    LivePartialTake,
)
from strategy_engine.strategies.ema_pullback.evaluation import (
    EmaPullbackEvaluation,
    evaluate_ema_pullback_frame,
)
from strategy_engine.strategies.ema_pullback.exits import PartialTakeRule
from strategy_engine.strategies.ema_pullback.live_projections.contracts import (
    EmaPullbackLiveEntryProjection,
)

_SUPPORTED_PROFILES = frozenset({"always_on", "aligned", "countertrend", "neutral"})


def _normalized_positive(value: float | None, *, field: str) -> str | None:
    if value is None:
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidRequestError(f"{field} must be a decimal") from exc
    if not decimal.is_finite() or decimal <= 0:
        return None
    return normalized_decimal_text(decimal)


def _profile_at(evaluation: EmaPullbackEvaluation, side: str, index: int) -> str:
    profiles = (
        evaluation.exit_policy.profile_long
        if side == "long"
        else evaluation.exit_policy.profile_short
    )
    try:
        profile = profiles[index]
    except IndexError as exc:
        raise InvalidRequestError("exit profile does not contain target index") from exc
    if profile not in _SUPPORTED_PROFILES:
        raise InvalidRequestError("unsupported locked exit profile", profile=profile)
    return profile


def _plan_for_side(
    evaluation: EmaPullbackEvaluation, side: str, index: int, target: int
) -> LiveEntryPlan | None:
    projected = evaluation.potential_entries.get(side)
    if projected is None:
        return None
    try:
        entry_raw = projected.entry_price[index]
        stop_raw = projected.stop_price[index]
        take_raw = projected.take_price[index]
    except IndexError as exc:
        raise InvalidRequestError("PotentialEntry does not contain target index") from exc
    return _plan_from_prices(evaluation, side, index, target, entry_raw, stop_raw, take_raw)


def _touch_trigger_plan_for_side(
    evaluation: EmaPullbackEvaluation,
    frame: FeatureFrameLike,
    side: str,
    index: int,
    target: int,
) -> LiveEntryPlan | None:
    """`touch_trigger` live-entry mode (`touch-signal-close-entry-v1`, D2):
    a plan only when the side's final entry mask (setups, vote, blockers,
    `touch_anchor`, risk) is true on the target bar, priced at the target
    bar close with that bar's exit-policy distances -- the same formula
    `potential_entries` applies to the anchor. Other triggers: no plan."""

    trigger = next((item for item in evaluation.triggers if item.side == side), None)
    entries = next((item for item in evaluation.entries if item.side == side), None)
    if trigger is None or entries is None or trigger.trigger.component_id != "touch_anchor":
        return None
    try:
        signal = entries.entry_allowed[index]
        close = frame_market_arrays(frame).values("close")[index]
        if side == "long":
            stop_distance = evaluation.exit_policy.stop_loss_distance_long[index]
            take_distance = evaluation.exit_policy.take_profit_distance_long[index]
        else:
            stop_distance = evaluation.exit_policy.stop_loss_distance_short[index]
            take_distance = evaluation.exit_policy.take_profit_distance_short[index]
    except IndexError as exc:
        raise InvalidRequestError("live evaluation does not contain target index") from exc
    if (
        not signal
        or stop_distance is None
        or take_distance is None
        or not all(isfinite(value) and value > 0 for value in (close, stop_distance, take_distance))
    ):
        return None
    if side == "long":
        stop, take = close - stop_distance, close + take_distance
    else:
        stop, take = close + stop_distance, close - take_distance
    return _plan_from_prices(evaluation, side, index, target, close, stop, take)


def _plan_from_prices(
    evaluation: EmaPullbackEvaluation,
    side: str,
    index: int,
    target: int,
    entry_raw: float | None,
    stop_raw: float | None,
    take_raw: float | None,
) -> LiveEntryPlan | None:
    entry = _normalized_positive(entry_raw, field="planned_entry_price")
    stop = _normalized_positive(stop_raw, field="initial_stop_price")
    take = _normalized_positive(take_raw, field="initial_take_price")
    if entry is None or stop is None or take is None:
        return None
    entry_decimal, stop_decimal, take_decimal = Decimal(entry), Decimal(stop), Decimal(take)
    valid = (
        stop_decimal < entry_decimal < take_decimal
        if side == "long"
        else take_decimal < entry_decimal < stop_decimal
    )
    if not valid:
        return None
    locked_profile = _profile_at(evaluation, side, index)
    partial_takes = _partial_takes(
        evaluation.exit_policy.partial_takes, side, index, locked_profile, entry_decimal
    )
    if partial_takes is None:
        return None
    return LiveEntryPlan(
        side=side,
        source_plan_bar_open_time_ms=target,
        planned_entry_price=entry,
        initial_stop_price=stop,
        initial_take_price=take,
        locked_exit_profile=locked_profile,
        partial_takes=partial_takes,
    )


def _partial_takes(
    rules: tuple[PartialTakeRule, ...],
    side: str,
    index: int,
    locked_profile: str,
    entry: Decimal,
) -> tuple[LivePartialTake, ...] | None:
    """Frozen leg prices of `always_on` + the locked profile on the plan
    bar (`frozen-partial-take-ladder-v1`, design D8): pct legs
    `entry * (1 ± pct)`, ATR legs `entry ± k*ATR` (the final take's
    formula). `None` (no plan for the side) when any leg in force has no
    valid positive profit-side price. Never compared with the final take.
    Ordered by distance from entry, ties by declared order."""

    sign = Decimal(1) if side == "long" else Decimal(-1)
    legs: list[tuple[Decimal, LivePartialTake]] = []
    for rule in rules:
        if rule.group not in ("always_on", locked_profile):
            continue
        if rule.pct is not None:
            distance: Decimal | None = entry * Decimal(repr(rule.pct))
        else:
            try:
                raw = rule.distance[index]
            except IndexError as exc:
                raise InvalidRequestError(
                    "partial take distance does not contain target index"
                ) from exc
            distance = None if raw is None else Decimal(repr(raw))
        if distance is None or not distance.is_finite() or distance <= 0:
            return None
        price = entry + sign * distance
        if price <= 0:
            return None
        legs.append(
            (
                distance,
                LivePartialTake(
                    take_id=rule.instance_id,
                    price=normalized_decimal_text(price),
                    fraction_of_initial=normalized_decimal_text(
                        Decimal(repr(rule.fraction_of_initial))
                    ),
                ),
            )
        )
    return tuple(leg for _, leg in sorted(legs, key=lambda item: item[0]))


class EmaPullbackLiveEntryProjectionAdapter:
    strategy_id = "ema_pullback"

    def __init__(self, *, live_entry_mode: LiveEntryMode = "ema_anchor") -> None:
        if live_entry_mode not in LIVE_ENTRY_MODES:
            raise ValueError(f"unsupported live_entry_mode: {live_entry_mode!r}")
        self._live_entry_mode = live_entry_mode

    def evaluate(
        self,
        request: LiveEntryProjectionRequest,
        bundle: LiveFeatureFrameBundle,
    ) -> EmaPullbackLiveEntryProjection:
        evaluation = evaluate_ema_pullback_frame(
            request.strategy, bundle.frame, bundle.planned_features
        )
        if self._live_entry_mode == "touch_trigger":
            return EmaPullbackLiveEntryProjection(
                plans_by_side={
                    side: _touch_trigger_plan_for_side(
                        evaluation,
                        bundle.frame,
                        side,
                        bundle.target_index,
                        request.target_bar_open_time_ms,
                    )
                    for side in ("long", "short")
                }
            )
        return EmaPullbackLiveEntryProjection(
            plans_by_side={
                side: _plan_for_side(
                    evaluation,
                    side,
                    bundle.target_index,
                    request.target_bar_open_time_ms,
                )
                for side in ("long", "short")
            }
        )
