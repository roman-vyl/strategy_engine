"""Deterministic coarse-grained batch strategy evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError, StrategyEngineError
from strategy_engine.ports.market_data import MarketDataPort
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.contracts import StrategyRangeBatchRequest, StrategyRangeRequest


@dataclass(frozen=True, slots=True)
class BatchVariantOutcome:
    variant_id: str
    result: Any | None
    error: dict[str, Any] | None


class EvaluateStrategyRangeBatch:
    def __init__(self, evaluator: EvaluateStrategyRange, market_data: MarketDataPort) -> None:
        self._evaluator = evaluator
        self._market_data = market_data

    def execute(self, request: StrategyRangeBatchRequest) -> tuple[BatchVariantOutcome, ...]:
        ids = [variant.variant_id for variant in request.variants]
        if not ids or len(ids) != len(set(ids)):
            raise InvalidRequestError("batch variants must be non-empty with unique variant_id")
        # batch-market-dataset-reuse: this call now owns the shared
        # acquisition, so it must validate the batch range itself rather
        # than relying on a downstream layer (HTTP adapter, MarketDataPort
        # implementation) to be the only place this is ever checked.
        request.time_range.validate_alignment(request.market.base_timeframe)
        # Acquire the shared market dataset exactly
        # once, outside and before the variant loop. A terminal failure here
        # (uncaught StrategyEngineError) fails the whole batch -- see
        # design.md Decision 2 -- rather than being retried independently per
        # variant. Same fail-closed provenance contract as single-range
        # evaluation: when the caller supplies expected_market_data_hash,
        # the shared acquisition is verified against it, not trusted
        # unconditionally.
        market_frame = self._market_data.load_range(
            request.market,
            request.time_range,
            expected_market_data_hash=request.expected_market_data_hash,
        )
        outcomes: list[BatchVariantOutcome] = []
        for variant in request.variants:
            try:
                result = self._evaluator.execute(
                    StrategyRangeRequest(
                        strategy=variant.strategy,
                        market=request.market,
                        time_range=request.time_range,
                        options=request.options,
                        market_frame=market_frame,
                        expected_market_data_hash=request.expected_market_data_hash,
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
