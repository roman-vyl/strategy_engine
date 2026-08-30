"""Strategy implementation ports."""

from __future__ import annotations

from typing import Any, Protocol

from strategy_engine.strategies.contracts import (
    HistoricalExecutionProjection,
    StrategyDiagnosticEvaluation,
    StrategyEvaluationExecution,
    StrategyRangeRequest,
    StrategyRangeResult,
)


class StrategyEvaluator(Protocol):
    def evaluate(self, request: StrategyRangeRequest) -> StrategyRangeResult: ...

    def evaluate_execution(self, request: StrategyRangeRequest) -> StrategyEvaluationExecution: ...

    def evaluate_execution_projection(
        self, request: StrategyRangeRequest
    ) -> HistoricalExecutionProjection: ...

    def evaluate_diagnostics(
        self, request: StrategyRangeRequest
    ) -> StrategyDiagnosticEvaluation: ...


class StrategyRegistryPort(Protocol):
    def list_definitions(self) -> tuple[dict[str, Any], ...]: ...

    def get_schema(self, strategy_id: str) -> dict[str, Any] | None: ...

    def evaluator(self, strategy_id: str) -> StrategyEvaluator | None: ...
