"""Strategy range evaluation orchestration."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import (
    HistoricalExecutionProjection,
    StrategyDiagnosticEvaluation,
    StrategyEvaluationExecution,
    StrategyRangeRequest,
)
from strategy_engine.strategies.ports import StrategyEvaluator, StrategyRegistryPort


class EvaluateStrategyRange:
    """Strategy range evaluation orchestration
    (`strategy-research-execution-contract-v1`,
    `compact-strategy-evaluation-boundary-v1`). `execute_projection` is
    the production path -- both `/strategy-evaluations/range` and
    `/strategy-evaluations/range-batch` call it (per variant, for
    batch) since I8. `execute` (the sparse `.v1`
    `StrategyEvaluationExecution` shape) is no longer reachable from any
    route -- private, in-process-only, kept for this repo's own test
    suite and any future regression comparison. `execute_diagnostics`
    is the separate, explicitly-requested path for dense per-bar
    diagnostic data, unaffected by any of this."""

    def __init__(
        self,
        registry: StrategyRegistryPort,
        validator: ValidateStrategySpec,
    ) -> None:
        self._registry = registry
        self._validator = validator

    def execute(self, request: StrategyRangeRequest) -> StrategyEvaluationExecution:
        """Legacy sparse `.v1` path. Not called by any HTTP route --
        both `/range` and `/range-batch` call `execute_projection`
        instead (I7/I8). Retained as private, in-process-only code."""

        evaluator = self._prepare(request)
        return evaluator.evaluate_execution(request)

    def execute_projection(self, request: StrategyRangeRequest) -> HistoricalExecutionProjection:
        """The production `.v2` path -- called by both
        `/strategy-evaluations/range` (I7) and
        `/strategy-evaluations/range-batch` (per variant, I8). See
        `strategy-research-execution-contract-v1`'s "Production /range
        route contract (I7 cutover)"/"Production /range-batch route
        contract (I8 cutover)" requirements."""

        evaluator = self._prepare(request)
        return evaluator.evaluate_execution_projection(request)

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
