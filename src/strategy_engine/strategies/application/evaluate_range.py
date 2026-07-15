"""Strategy range evaluation orchestration."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import StrategyRangeRequest, StrategyRangeResult
from strategy_engine.strategies.ports import StrategyRegistryPort


class EvaluateStrategyRange:
    def __init__(
        self,
        registry: StrategyRegistryPort,
        validator: ValidateStrategySpec,
    ) -> None:
        self._registry = registry
        self._validator = validator

    def execute(self, request: StrategyRangeRequest) -> StrategyRangeResult:
        request.time_range.validate_alignment(request.market.base_timeframe)
        evaluator = self._registry.evaluator(request.strategy.strategy_id)
        if evaluator is None:
            raise UnsupportedCapabilityError(f"strategy:{request.strategy.strategy_id}")
        self._validator.execute(request.strategy)
        return evaluator.evaluate(request)
