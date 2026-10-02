"""Stable transport serialization for strategy range results."""

from __future__ import annotations

from math import isfinite

from strategy_engine.strategies.contracts import (
    ExecutableEntryOpportunity,
    ExitAttribution,
    HistoricalExecutionProjection,
    HistoricalManagedProjection,
    InitialProtectionLeg,
    ManagedConditionSeries,
    ManagedRule,
    ManagedTransitionPath,
    SignalExitEvent,
    SignalExitProjection,
    StrategyDecisionEvent,
    StrategyDiagnosticEvaluation,
    StrategyEvaluationExecution,
    StrategyRangeResult,
)


def serialize_strategy_result(result: StrategyRangeResult) -> dict[str, object]:
    feature_time = result.features.get("time_ms", []) if isinstance(result.features, dict) else []
    market_data_hash = (
        result.features.get("market_data_hash", "") if isinstance(result.features, dict) else ""
    )
    return {
        "contract_version": "strategy_evaluation.v1",
        "strategy_id": result.strategy_id,
        "config_hash": result.config_hash,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
            "bar_count": len(feature_time),
            "market_data_hash": market_data_hash,
        },
        "features": result.features,
        "contexts": result.contexts,
        "entries": result.entries,
        "potential_entries": result.potential_entries,
        "exit_policy": result.exit_policy,
        "component_evidence": result.component_evidence,
        "validity": result.validity,
        "state_artifact": result.state_artifact,
        "warnings": list(result.warnings),
    }


def _serialize_decision_event(event: StrategyDecisionEvent) -> dict[str, object]:
    return {
        "bar_index": event.bar_index,
        "entry": (
            {
                "side": event.entry.side,
                "stop_loss_ratio": event.entry.stop_loss_ratio,
                "take_profit_ratio": event.entry.take_profit_ratio,
            }
            if event.entry is not None
            else None
        ),
        "signal_exit": (
            {"long": event.signal_exit.long, "short": event.signal_exit.short}
            if event.signal_exit is not None
            else None
        ),
        "stop_ready": (
            {"long": event.stop_ready.long, "short": event.stop_ready.short}
            if event.stop_ready is not None
            else None
        ),
    }


def serialize_strategy_evaluation_execution(
    result: StrategyEvaluationExecution,
) -> dict[str, object]:
    """The mandatory sparse execution contract
    (`strategy-research-execution-contract-v1`,
    `compact-strategy-evaluation-boundary-v1`). No `time_ms` array --
    `bar_index` + `market_data_hash` + `bar_count` is the join key back
    to the caller's own market data. No diagnostic fields."""

    return {
        "contract_version": "strategy_evaluation_execution.v1",
        "strategy_id": result.strategy_id,
        "config_hash": result.config_hash,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
            "bar_count": result.bar_count,
            "market_data_hash": result.market_data_hash,
        },
        "decision_events": [_serialize_decision_event(event) for event in result.decision_events],
        "warnings": list(result.warnings),
    }


def _serialize_attribution(attribution: ExitAttribution) -> dict[str, object]:
    return {
        "rule_id": attribution.rule_id,
        "component_id": attribution.component_id,
        "exit_kind": attribution.exit_kind,
    }


def _serialize_leg(leg: InitialProtectionLeg | None) -> dict[str, object] | None:
    if leg is None:
        return None
    return {"ratio": leg.ratio, "attribution": _serialize_attribution(leg.attribution)}


def _serialize_opportunity(opportunity: ExecutableEntryOpportunity) -> dict[str, object]:
    wire: dict[str, object] = {
        "bar_index": opportunity.bar_index,
        "side": opportunity.side,
        "locked_exit_profile": opportunity.locked_exit_profile,
        "initial_stop": _serialize_leg(opportunity.initial_stop),
        "initial_take": _serialize_leg(opportunity.initial_take),
    }
    if opportunity.partial_takes:
        # Omitted when empty: existing specs stay byte-identical on `.v2`
        # (`frozen-partial-take-ladder-v1`, design D6).
        wire["partial_takes"] = [
            {
                "take_id": leg.take_id,
                "ratio": leg.ratio,
                "fraction_of_initial": leg.fraction_of_initial,
                "attribution": _serialize_attribution(leg.attribution),
            }
            for leg in opportunity.partial_takes
        ]
    return wire


def _serialize_signal_exit_events(events: tuple[SignalExitEvent, ...]) -> list[dict[str, object]]:
    return [
        {
            "bar_index": event.bar_index,
            "candidates": [
                {"attribution": _serialize_attribution(candidate.attribution)}
                for candidate in event.candidates
            ],
        }
        for event in events
    ]


def _serialize_signal_exit_projection(projection: SignalExitProjection) -> dict[str, object]:
    return {
        "long": {
            profile: _serialize_signal_exit_events(events)
            for profile, events in projection.long.items()
        },
        "short": {
            profile: _serialize_signal_exit_events(events)
            for profile, events in projection.short.items()
        },
    }


def _serialize_condition_series(series: ManagedConditionSeries) -> dict[str, object]:
    return {"long": list(series.long), "short": list(series.short)}


def _serialize_distance(value: float) -> float | None:
    return value if isfinite(value) else None


def _serialize_path(path: ManagedTransitionPath) -> dict[str, object]:
    return {
        "path_id": path.path_id,
        "condition_id": path.condition_id,
        "thresholds": [
            {"distance_id": item.distance_id, "trade_metric": item.trade_metric}
            for item in path.thresholds
        ],
        "at_least": None
        if path.at_least is None
        else {
            "k": path.at_least.k,
            "terms": [
                {
                    "condition_id": term.condition_id,
                    "distance_id": term.distance_id,
                    "trade_metric": term.trade_metric,
                }
                for term in path.at_least.terms
            ],
        },
    }


def _serialize_rule(rule: ManagedRule) -> dict[str, object]:
    """`historical-managed-projection-v1`'s discriminated `rules[]` wire
    shape (design.md D6a): a `kind` tag plus that variant's own opaque/
    generic fields only -- never a `component_id` or raw strategy
    parameter."""

    if rule.kind == "phase_transition":
        wire: dict[str, object] = {
            "kind": "phase_transition",
            "rule_id": rule.rule_id,
            "target_phase": rule.target_phase,
            "condition_id": rule.condition_id,
            "distance_id": rule.distance_id,
            "trade_metric": rule.trade_metric,
        }
        # Omitted for atomic rules: their bytes stay unchanged
        # (composite-managed-phase-condition-v1 design D6).
        if rule.paths is not None:
            wire["paths"] = [_serialize_path(path) for path in rule.paths]
        return wire
    if rule.kind == "take_action":
        return {
            "kind": "take_action",
            "rule_id": rule.rule_id,
            "activation_phase": rule.activation_phase,
            "resulting_profile": rule.resulting_profile,
        }
    if rule.kind == "stop_action":
        wire = {
            "kind": "stop_action",
            "rule_id": rule.rule_id,
            "activation_phase": rule.activation_phase,
            "distance_id": rule.distance_id,
        }
        if rule.stop_formula is not None:
            wire["stop_formula"] = rule.stop_formula
            wire["trigger_distance_id"] = rule.trigger_distance_id
        return wire
    return {
        "kind": "runtime_exit",
        "rule_id": rule.rule_id,
        "activation_phase": rule.activation_phase,
        "condition_id": rule.condition_id,
        "confirm_bars": rule.confirm_bars,
        "exit_class": rule.exit_class,
    }


def _serialize_managed_projection(
    managed: HistoricalManagedProjection | None,
) -> dict[str, object] | None:
    if managed is None:
        return None
    return {
        "conditions": {
            condition_id: _serialize_condition_series(series)
            for condition_id, series in managed.conditions.items()
        },
        "distances": {
            distance_id: [_serialize_distance(value) for value in values]
            for distance_id, values in managed.distances.items()
        },
        "rules": [_serialize_rule(rule) for rule in managed.rules],
    }


def serialize_historical_execution_projection(
    result: HistoricalExecutionProjection,
) -> dict[str, object]:
    """The production `.v2` execution contract
    (`strategy-research-execution-contract-v1`,
    `compact-strategy-evaluation-boundary-v1` I7/I8) -- executable entry
    opportunities with locked exit profile and attributed initial
    stop/take, per-profile-indexed signal-exit events with attribution.
    Used by both `/strategy-evaluations/range` (I7, one envelope per
    response) and the streamed `/strategy-evaluations/range-batch`
    (I8, one envelope per `result` field in each streamed element) --
    both routes reach it via `EvaluateStrategyRange.execute_projection`,
    never via the legacy `execute()`/sparse `.v1` path."""

    return {
        "contract_version": "strategy_evaluation_execution.v2",
        "strategy_id": result.strategy_id,
        "config_hash": result.config_hash,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
            "bar_count": result.bar_count,
            "market_data_hash": result.market_data_hash,
        },
        "entry_opportunities": [
            _serialize_opportunity(opportunity) for opportunity in result.entry_opportunities
        ],
        "signal_exit_events": _serialize_signal_exit_projection(result.signal_exit_events),
        "warnings": list(result.warnings),
        "managed": _serialize_managed_projection(result.managed),
    }


def serialize_batch_variant_outcome(
    variant_id: str,
    result: HistoricalExecutionProjection | None,
    error: dict[str, object] | None,
) -> dict[str, object]:
    """One `/strategy-evaluations/range-batch` streamed element (I8,
    `compact-strategy-evaluation-boundary-v1`): `{variant_id, result,
    error}`, `variant_id` always present, exactly one of `result`/`error`
    non-null. `result`, when present, is the unwrapped canonical `.v2`
    envelope -- the same shape `serialize_historical_execution_projection`
    produces for `/range`, not a batch-specific reduction of it."""

    return {
        "variant_id": variant_id,
        "result": serialize_historical_execution_projection(result) if result is not None else None,
        "error": error,
    }


def serialize_strategy_diagnostic_evaluation(
    result: StrategyDiagnosticEvaluation,
) -> dict[str, object]:
    """The separate, explicitly-requested diagnostic contract -- dense
    per-bar data, never returned as a side effect of an execution-
    contract request (`compact-strategy-evaluation-boundary-v1`)."""

    return {
        "contract_version": "strategy_diagnostic_evaluation.v1",
        "strategy_id": result.strategy_id,
        "config_hash": result.config_hash,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
            "bar_count": result.bar_count,
            "market_data_hash": result.market_data_hash,
        },
        "features": result.features,
        "contexts": result.contexts,
        "potential_entries": result.potential_entries,
        "component_evidence": result.component_evidence,
        "warnings": list(result.warnings),
    }
