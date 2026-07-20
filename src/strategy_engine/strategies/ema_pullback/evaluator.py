"""EMA Pullback range evaluator."""

from __future__ import annotations

from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.contracts import IndicatorRangeRequest
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import StrategyRangeRequest, StrategyRangeResult
from strategy_engine.strategies.ema_pullback.evaluation import evaluate_ema_pullback_frame
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

    def evaluate(self, request: StrategyRangeRequest) -> StrategyRangeResult:
        planned = self._feature_planner.execute(request.strategy)
        frame = self._indicator_evaluator.execute(
            IndicatorRangeRequest(
                market=request.market,
                time_range=request.time_range,
                plan=planned.indicator_plan,
                expected_market_data_hash=request.expected_market_data_hash,
            )
        )
        evaluation = evaluate_ema_pullback_frame(request.strategy, frame, planned)
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
                "mappings": planned.to_wire(),
            }
        return StrategyRangeResult(
            strategy_id=request.strategy.strategy_id,
            strategy_version=request.strategy.strategy_version,
            instance_id=request.strategy.instance_id,
            config_hash=request.strategy.config_hash,
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
