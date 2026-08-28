"""EMA Pullback range evaluator."""

from __future__ import annotations

from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.contracts import FeatureFrame, IndicatorRangeRequest
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import (
    StrategyDiagnosticEvaluation,
    StrategyEvaluationExecution,
    StrategyRangeRequest,
    StrategyRangeResult,
    strategy_config_hash,
)
from strategy_engine.strategies.decision_events import build_decision_events
from strategy_engine.strategies.ema_pullback.evaluation import (
    EmaPullbackEvaluation,
    evaluate_ema_pullback_frame,
)
from strategy_engine.strategies.ema_pullback.potential_entries import potential_entries_to_wire


class EmaPullbackRangeEvaluator:
    """Evaluate the complete EMA Pullback strategy range once."""

    def __init__(
        self,
        feature_planner: BuildStrategyFeaturePlan,
        indicator_evaluator: EvaluateIndicatorRange,
    ) -> None:
        self._feature_planner = feature_planner
        self._indicator_evaluator = indicator_evaluator

    def _evaluate_frame(
        self, request: StrategyRangeRequest
    ) -> tuple[FeatureFrame, EmaPullbackEvaluation]:
        planned = self._feature_planner.execute(request.strategy)
        frame = self._indicator_evaluator.execute(
            IndicatorRangeRequest(
                market=request.market,
                time_range=request.time_range,
                plan=planned.indicator_plan,
                expected_market_data_hash=request.expected_market_data_hash,
                market_frame=request.market_frame,
            )
        )
        evaluation = evaluate_ema_pullback_frame(request.strategy, frame, planned)
        return frame, evaluation

    def evaluate_execution(self, request: StrategyRangeRequest) -> StrategyEvaluationExecution:
        """The mandatory execution contract -- sparse decision events only,
        no dense per-bar arrays, no diagnostic data
        (`strategy-research-execution-contract-v1`,
        `compact-strategy-evaluation-boundary-v1`)."""

        frame, evaluation = self._evaluate_frame(request)
        entries_long = next(
            (item.entry_allowed for item in evaluation.entries if item.side == "long"),
            tuple(False for _ in frame.time_ms),
        )
        entries_short = next(
            (item.entry_allowed for item in evaluation.entries if item.side == "short"),
            tuple(False for _ in frame.time_ms),
        )
        exit_policy = evaluation.exit_policy
        decision_events = build_decision_events(
            entries_long=entries_long,
            entries_short=entries_short,
            stop_loss_ratio_long=exit_policy.stop_loss_ratio_long,
            stop_loss_ratio_short=exit_policy.stop_loss_ratio_short,
            take_profit_ratio_long=exit_policy.take_profit_ratio_long,
            take_profit_ratio_short=exit_policy.take_profit_ratio_short,
            signal_exit_long=exit_policy.signal_exit_long,
            signal_exit_short=exit_policy.signal_exit_short,
            stop_ready_long=exit_policy.stop_ready_long,
            stop_ready_short=exit_policy.stop_ready_short,
        )
        return StrategyEvaluationExecution(
            strategy_id=request.strategy.strategy_id,
            config_hash=strategy_config_hash(request.strategy),
            market=request.market,
            requested_range=request.time_range,
            market_data_hash=frame.market_data_hash,
            bar_count=len(frame.time_ms),
            decision_events=decision_events,
            warnings=(
                "managed exit policy is available through /v1/strategy-evaluations/managed-replay",
            ),
        )

    def evaluate_diagnostics(self, request: StrategyRangeRequest) -> StrategyDiagnosticEvaluation:
        """Dense per-bar diagnostic trace -- only reachable via the
        separate, explicitly-requested diagnostic-evaluation entrypoint,
        never as a side effect of an execution-contract request."""

        frame, evaluation = self._evaluate_frame(request)
        return StrategyDiagnosticEvaluation(
            strategy_id=request.strategy.strategy_id,
            config_hash=strategy_config_hash(request.strategy),
            market=request.market,
            requested_range=request.time_range,
            market_data_hash=frame.market_data_hash,
            bar_count=len(frame.time_ms),
            features={
                "time_ms": list(frame.time_ms),
                "series": {key: list(values) for key, values in frame.series.items()},
                "validity": {
                    key: {
                        "valid_from_ms": value.valid_from_ms,
                        "warmup_bars": value.warmup_bars,
                        "complete": value.complete,
                        "reason": value.reason,
                    }
                    for key, value in frame.validity.items()
                },
                "plan_hash": frame.plan_hash,
                "market_data_hash": frame.market_data_hash,
                "mappings": self._feature_planner.execute(request.strategy).to_wire(),
            },
            contexts=evaluation.contexts.to_wire(),
            potential_entries=potential_entries_to_wire(evaluation.potential_entries),
            component_evidence={
                "context_consumption": [item.to_wire() for item in evaluation.consumption],
                "direction_blockers": [item.to_wire() for item in evaluation.direction_blockers],
                "setups": [item.to_wire() for item in evaluation.setups],
                "triggers": [item.to_wire() for item in evaluation.triggers],
                "risk_entries": [item.to_wire() for item in evaluation.entries],
                "exit_policy": evaluation.exit_policy.to_wire(),
            },
            warnings=(
                "managed exit policy is available through /v1/strategy-evaluations/managed-replay",
            ),
        )

    def evaluate(self, request: StrategyRangeRequest) -> StrategyRangeResult:
        """Legacy dense contract -- retained until research_service's
        companion change (`compact-strategy-evaluation-boundary-v1`)
        cuts existing routes over to `evaluate_execution`/
        `evaluate_diagnostics`. Not the mandatory path going forward."""

        frame, evaluation = self._evaluate_frame(request)
        features: dict[str, object] = {}
        if request.options.include_features:
            features = {
                "time_ms": list(frame.time_ms),
                "series": {key: list(values) for key, values in frame.series.items()},
                "validity": {
                    key: {
                        "valid_from_ms": value.valid_from_ms,
                        "warmup_bars": value.warmup_bars,
                        "complete": value.complete,
                        "reason": value.reason,
                    }
                    for key, value in frame.validity.items()
                },
                "plan_hash": frame.plan_hash,
                "market_data_hash": frame.market_data_hash,
                "mappings": self._feature_planner.execute(request.strategy).to_wire(),
            }
        return StrategyRangeResult(
            strategy_id=request.strategy.strategy_id,
            config_hash=strategy_config_hash(request.strategy),
            market=request.market,
            requested_range=request.time_range,
            features=features,
            contexts=(
                evaluation.contexts.to_wire() if request.options.include_contexts else {}
            ),
            entries={
                side: next(
                    (list(item.entry_allowed) for item in evaluation.entries if item.side == side),
                    [False] * len(frame.time_ms),
                )
                for side in ("long", "short")
            },
            potential_entries=potential_entries_to_wire(evaluation.potential_entries),
            exit_policy=evaluation.exit_policy.to_wire(),
            component_evidence=(
                {
                    "context_consumption": [
                        item.to_wire() for item in evaluation.consumption
                    ],
                    "direction_blockers": [
                        item.to_wire() for item in evaluation.direction_blockers
                    ],
                    "setups": [item.to_wire() for item in evaluation.setups],
                    "triggers": [item.to_wire() for item in evaluation.triggers],
                    "risk_entries": [item.to_wire() for item in evaluation.entries],
                    "exit_policy": evaluation.exit_policy.to_wire(),
                }
                if request.options.include_component_evidence
                else {}
            ),
            validity={
                "stage": "decisions_ready",
                "features_ready": True,
                "contexts_ready": True,
                "context_consumption_ready": True,
                "direction_blockers_ready": True,
                "setups_ready": True,
                "triggers_ready": True,
                "risk_ready": True,
                "entries_ready": True,
                "exits_ready": True,
                "decisions_ready": True,
            },
            state_artifact=None,
            warnings=(
                "managed exit policy is available through /v1/strategy-evaluations/managed-replay",
            ),
        )
