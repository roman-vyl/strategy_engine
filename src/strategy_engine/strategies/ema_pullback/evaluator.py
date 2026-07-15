"""Feature and context stage ema_pullback range evaluator."""

from __future__ import annotations

from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.contracts import IndicatorRangeRequest
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import StrategyRangeRequest, StrategyRangeResult
from strategy_engine.strategies.ema_pullback.context_consumption import (
    build_context_consumption_evidence,
)
from strategy_engine.strategies.ema_pullback.contexts import build_context_bundle
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.exits import evaluate_exit_policy
from strategy_engine.strategies.ema_pullback.risk import evaluate_risk_and_entries
from strategy_engine.strategies.ema_pullback.setups import evaluate_setups
from strategy_engine.strategies.ema_pullback.triggers import evaluate_triggers


class EmaPullbackRangeEvaluator:
    """Evaluate strategy-owned features and contexts; decisions are not ported yet."""

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
        context_bundle = build_context_bundle(
            request.strategy.raw_spec,
            frame,
            planned,
        )
        consumption = build_context_consumption_evidence(request.strategy.raw_spec, context_bundle)
        direction_blockers = evaluate_direction_and_blockers(
            request.strategy.raw_spec, frame, planned, consumption
        )
        setups = evaluate_setups(
            request.strategy.raw_spec,
            frame,
            planned,
            consumption,
            direction_blockers,
        )
        triggers = evaluate_triggers(
            request.strategy.raw_spec,
            frame,
            planned,
            setups,
        )
        entries = evaluate_risk_and_entries(
            request.strategy.raw_spec,
            triggers,
        )
        exit_policy = evaluate_exit_policy(
            request.strategy.raw_spec,
            frame,
            planned,
            consumption,
        )
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
            contexts=(context_bundle.to_wire() if request.options.include_contexts else {}),
            entries={
                side: next(
                    (list(item.entry_allowed) for item in entries if item.side == side),
                    [False] * len(frame.time_ms),
                )
                for side in ("long", "short")
            },
            exit_policy=exit_policy.to_wire(),
            component_evidence=(
                {
                    "context_consumption": [item.to_wire() for item in consumption],
                    "direction_blockers": [item.to_wire() for item in direction_blockers],
                    "setups": [item.to_wire() for item in setups],
                    "triggers": [item.to_wire() for item in triggers],
                    "risk_entries": [item.to_wire() for item in entries],
                    "exit_policy": exit_policy.to_wire(),
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
