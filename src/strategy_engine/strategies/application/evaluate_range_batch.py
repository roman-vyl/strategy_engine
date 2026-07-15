"""Deterministic coarse-grained batch strategy evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError, StrategyEngineError
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.contracts import StrategyRangeBatchRequest, StrategyRangeRequest


@dataclass(frozen=True, slots=True)
class BatchVariantOutcome:
    variant_id: str
    result: Any | None
    error: dict[str, Any] | None


class EvaluateStrategyRangeBatch:
    def __init__(self, evaluator: EvaluateStrategyRange) -> None:
        self._evaluator = evaluator

    def execute(self, request: StrategyRangeBatchRequest) -> tuple[BatchVariantOutcome, ...]:
        ids = [variant.variant_id for variant in request.variants]
        if not ids or len(ids) != len(set(ids)):
            raise InvalidRequestError("batch variants must be non-empty with unique variant_id")
        outcomes: list[BatchVariantOutcome] = []
        for variant in request.variants:
            try:
                result = self._evaluator.execute(
                    StrategyRangeRequest(
                        strategy=variant.strategy,
                        market=request.market,
                        time_range=request.time_range,
                        options=request.options,
                    )
                )
                outcomes.append(BatchVariantOutcome(variant.variant_id, result, None))
            except StrategyEngineError as exc:
                outcomes.append(
                    BatchVariantOutcome(
                        variant.variant_id,
                        None,
                        {"error": exc.code, "message": exc.message, "details": exc.details},
                    )
                )
        return tuple(outcomes)
