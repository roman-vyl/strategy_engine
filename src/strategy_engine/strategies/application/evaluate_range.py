"""Strategy range evaluation orchestration."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import (
    StrategyDiagnosticEvaluation,
    StrategyEvaluationExecution,
    StrategyRangeRequest,
)
from strategy_engine.strategies.ports import StrategyEvaluator, StrategyRegistryPort


class EvaluateStrategyRange:
    """The mandatory execution-contract path
    (`strategy-research-execution-contract-v1`,
    `compact-strategy-evaluation-boundary-v1`) -- `execute` returns the
    sparse `StrategyEvaluationExecution`, never dense diagnostics.
    `execute_diagnostics` is the separate, explicitly-requested path for
    dense per-bar diagnostic data."""

    def __init__(
        self,
        registry: StrategyRegistryPort,
        validator: ValidateStrategySpec,
    ) -> None:
        self._registry = registry
        self._validator = validator

    def execute(self, request: StrategyRangeRequest) -> StrategyEvaluationExecution:
        evaluator = self._prepare(request)
        return evaluator.evaluate_execution(request)

    def execute_diagnostics(self, request: StrategyRangeRequest) -> StrategyDiagnosticEvaluation:
        evaluator = self._prepare(request)
        return evaluator.evaluate_diagnostics(request)

    def _prepare(self, request: StrategyRangeRequest) -> StrategyEvaluator:
        request.time_range.validate_alignment(request.market.base_timeframe)
        evaluator = self._registry.evaluator(request.strategy.strategy_id)
        if evaluator is None:
            raise UnsupportedCapabilityError(f"strategy:{request.strategy.strategy_id}")
        self._validator.execute(request.strategy)
        return evaluator
