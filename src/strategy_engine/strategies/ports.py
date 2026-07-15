"""Strategy implementation ports."""

from __future__ import annotations

from typing import Any, Protocol

from strategy_engine.strategies.contracts import StrategyRangeRequest, StrategyRangeResult


class StrategyEvaluator(Protocol):
    def evaluate(self, request: StrategyRangeRequest) -> StrategyRangeResult: ...


class StrategyRegistryPort(Protocol):
    def list_definitions(self) -> tuple[dict[str, Any], ...]: ...

    def get_schema(self, strategy_id: str) -> dict[str, Any] | None: ...

    def evaluator(self, strategy_id: str) -> StrategyEvaluator | None: ...
