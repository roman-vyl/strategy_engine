"""Stable transport serialization for strategy range results."""

from __future__ import annotations

from strategy_engine.strategies.contracts import (
    ExecutableEntryOpportunity,
    ExitAttribution,
    HistoricalExecutionProjection,
    InitialProtectionLeg,
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
    return {
        "bar_index": opportunity.bar_index,
        "side": opportunity.side,
        "locked_exit_profile": opportunity.locked_exit_profile,
        "initial_stop": _serialize_leg(opportunity.initial_stop),
        "initial_take": _serialize_leg(opportunity.initial_take),
    }


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


def serialize_historical_execution_projection(
    result: HistoricalExecutionProjection,
) -> dict[str, object]:
    """The production `.v2` execution contract
    (`strategy-research-execution-contract-v1`,
    `compact-strategy-evaluation-boundary-v1` I7) -- executable entry
    opportunities with locked exit profile and attributed initial
    stop/take, per-profile-indexed signal-exit events with attribution.
    Only reachable via `/strategy-evaluations/range`'s new
    `execute_projection` path, never via `/range-batch`."""

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
