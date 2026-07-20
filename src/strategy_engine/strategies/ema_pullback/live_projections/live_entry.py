"""EMA Pullback live-entry projection adapter."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.strategies.application.load_live_feature_frame import LiveFeatureFrameBundle
from strategy_engine.strategies.contracts import LiveEntryPlan, LiveEntryProjectionRequest
from strategy_engine.strategies.ema_pullback.evaluation import (
    EmaPullbackEvaluation,
    evaluate_ema_pullback_frame,
)
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
    return LiveEntryPlan(
        side=side,
        source_plan_bar_open_time_ms=target,
        planned_entry_price=entry,
        initial_stop_price=stop,
        initial_take_price=take,
        locked_exit_profile=_profile_at(evaluation, side, index),
    )


class EmaPullbackLiveEntryProjectionAdapter:
    strategy_id = "ema_pullback"

    def evaluate(
        self,
        request: LiveEntryProjectionRequest,
        bundle: LiveFeatureFrameBundle,
    ) -> EmaPullbackLiveEntryProjection:
        evaluation = evaluate_ema_pullback_frame(
            request.strategy, bundle.frame, bundle.planned_features
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
