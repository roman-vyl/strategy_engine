"""EMA Pullback confirmed-open projection adapter."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError, TradeHistoryUnavailableError
from strategy_engine.domain.values import normalized_decimal_text, parse_decimal_text
from strategy_engine.strategies.application.load_live_feature_frame import LiveFeatureFrameBundle
from strategy_engine.strategies.contracts import OpenTradeProjectionRequest
from strategy_engine.strategies.ema_pullback.evaluation import (
    EmaPullbackEvaluation,
    evaluate_ema_pullback_frame,
)
from strategy_engine.strategies.ema_pullback.live_projections.contracts import (
    EmaPullbackCloseSignal,
    EmaPullbackDesiredProtection,
    EmaPullbackOpenTradeDiagnostics,
    EmaPullbackOpenTradeProjection,
)
from strategy_engine.strategies.ema_pullback.managed import (
    StartAfterEntryManagedProjection,
    evaluate_start_after_entry_managed_projection,
)


def _text(value: float) -> str:
    return normalized_decimal_text(Decimal(str(value)))


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _rules_for_locked_profile(
    raw_spec: Mapping[str, Any], locked_profile: str
) -> tuple[Mapping[str, Any], ...]:
    management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    policy = _mapping(management.get("exit_policy", {}), "exit_policy")
    always = _mapping(policy.get("always_on", {}), "exit_policy.always_on")
    profiles = _mapping(policy.get("profiles", {}), "exit_policy.profiles")
    profile = _mapping(
        profiles.get(locked_profile, {}), f"exit_policy.profiles.{locked_profile}"
    )
    always_rules = always.get("exits", [])
    profile_rules = profile.get("exits", [])
    if not isinstance(always_rules, list) or not isinstance(profile_rules, list):
        raise InvalidRequestError("exit policy rules must be lists")
    return tuple(_mapping(item, "exit rule") for item in (*always_rules, *profile_rules))


def _standard_signal_candidates(
    evaluation: EmaPullbackEvaluation,
    raw_spec: Mapping[str, Any],
    *,
    side: str,
    locked_profile: str,
    target_index: int,
) -> tuple[tuple[str, str], ...]:
    by_profile = (
        evaluation.exit_policy.signal_by_profile_long
        if side == "long"
        else evaluation.exit_policy.signal_by_profile_short
    )
    try:
        profile_signal = by_profile[locked_profile][target_index]
    except (KeyError, IndexError) as exc:
        raise InvalidRequestError(
            "locked exit profile does not contain target signal"
        ) from exc
    if not profile_signal:
        return ()
    evidence_by_instance = {
        item.instance_id: item
        for item in evaluation.exit_policy.rule_evidence
        if item.exit_kind == "signal" and item.side == side and item.signal is not None
    }
    candidates: list[tuple[str, str]] = []
    for rule in _rules_for_locked_profile(raw_spec, locked_profile):
        if str(rule.get("exit_kind", "signal")) != "signal":
            continue
        instance_id = str(rule.get("instance_id", ""))
        evidence = evidence_by_instance.get(instance_id)
        if evidence is None:
            continue
        try:
            active = evidence.signal[target_index]  # type: ignore[index]
        except IndexError as exc:
            raise InvalidRequestError(
                "signal evidence does not contain target index"
            ) from exc
        if active:
            candidates.append((instance_id, evidence.component_id))
    return tuple(candidates)


def _runtime_candidates(
    raw_spec: Mapping[str, Any], projection: StartAfterEntryManagedProjection
) -> tuple[tuple[str, str], ...]:
    management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    exit_management = _mapping(management.get("exit_management", {}), "exit_management")
    raw_rules = exit_management.get("runtime_exits", [])
    if not isinstance(raw_rules, list):
        raise InvalidRequestError("runtime_exits must be a list")
    rules = {
        str(rule.get("rule_id", "")): str(rule.get("component_id", ""))
        for item in raw_rules
        for rule in (_mapping(item, "runtime exit"),)
    }
    return tuple(
        (rule_id, rules.get(rule_id, ""))
        for rule_id in projection.replay.final_state.active_runtime_exit_rules
    )


def _compose_close_signal(
    *,
    runtime_candidates: tuple[tuple[str, str], ...],
    standard_candidates: tuple[tuple[str, str], ...],
) -> EmaPullbackCloseSignal:
    if runtime_candidates:
        rule_id, component_id = sorted(runtime_candidates, key=lambda item: item[0])[0]
        return EmaPullbackCloseSignal(
            True, f"runtime_exit:{rule_id}", component_id or None, "managed"
        )
    if standard_candidates:
        instance_id, component_id = sorted(standard_candidates, key=lambda item: item[0])[0]
        return EmaPullbackCloseSignal(
            True, f"signal:{instance_id}", component_id or None, "exit_policy"
        )
    return EmaPullbackCloseSignal(False, None, None, None)


class EmaPullbackOpenTradeProjectionAdapter:
    strategy_id = "ema_pullback"

    def evaluate(
        self,
        request: OpenTradeProjectionRequest,
        bundle: LiveFeatureFrameBundle,
    ) -> EmaPullbackOpenTradeProjection:
        receipt = request.executed_trade_receipt
        try:
            bundle.frame.time_ms.index(receipt.source_plan_bar_open_time_ms)
            bundle.frame.time_ms.index(receipt.entry_bar_open_time_ms)
        except ValueError as exc:
            raise TradeHistoryUnavailableError(
                source_plan_bar_open_time_ms=receipt.source_plan_bar_open_time_ms,
                entry_bar_open_time_ms=receipt.entry_bar_open_time_ms,
                target_bar_open_time_ms=request.target_bar_open_time_ms,
            ) from exc
        evaluation = evaluate_ema_pullback_frame(
            request.strategy, bundle.frame, bundle.planned_features
        )
        managed = evaluate_start_after_entry_managed_projection(
            request.strategy.raw_spec,
            bundle.frame,
            bundle.planned_features,
            trade_id=receipt.trade_id,
            side=receipt.side,  # type: ignore[arg-type]
            entry_time_ms=receipt.entry_bar_open_time_ms,
            planned_entry_price=float(parse_decimal_text(receipt.planned_entry_price)),
            initial_stop_price=float(parse_decimal_text(receipt.initial_stop_price)),
            initial_take_price=float(parse_decimal_text(receipt.initial_take_price)),
            target_time_ms=request.target_bar_open_time_ms,
        )
        standard = _standard_signal_candidates(
            evaluation,
            request.strategy.raw_spec,
            side=receipt.side,
            locked_profile=receipt.locked_exit_profile,
            target_index=bundle.target_index,
        )
        runtime = _runtime_candidates(request.strategy.raw_spec, managed)
        state = managed.replay.final_state
        return EmaPullbackOpenTradeProjection(
            desired_protection=EmaPullbackDesiredProtection(
                stop_price=_text(managed.desired_stop_price),
                take_price=(
                    _text(managed.desired_take_price)
                    if managed.desired_take_price is not None
                    else None
                ),
            ),
            close_signal=_compose_close_signal(
                runtime_candidates=runtime,
                standard_candidates=standard,
            ),
            diagnostics=EmaPullbackOpenTradeDiagnostics(
                phase=state.phase,
                max_phase_reached=state.max_phase_reached,
                bars_in_trade=state.bars_in_trade,
                mfe_pct=_text(state.mfe_pct),
                mae_pct=_text(state.mae_pct),
                managed_events=tuple(event.to_wire() for event in managed.replay.events),
            ),
        )
