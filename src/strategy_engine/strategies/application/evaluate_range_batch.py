"""Deterministic coarse-grained batch strategy evaluation.

I8 (`compact-strategy-evaluation-boundary-v1`): streamed `.v2` per-variant
evaluation, not a buffered `.v1` aggregate. `execute()` runs shared
acquisition/validation synchronously (so a failure there is a normal,
whole-request exception, not something that can happen mid-stream) and
returns a not-yet-started generator; the caller (the HTTP route) iterates
it to actually drive per-variant evaluation and streaming.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError, StrategyEngineError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.indicators.evaluation_context import EvaluationContext
from strategy_engine.ports.market_data import MarketDataPort
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.contracts import (
    HistoricalExecutionProjection,
    StrategyRangeBatchRequest,
    StrategyRangeRequest,
)


@dataclass(frozen=True, slots=True)
class BatchVariantOutcome:
    variant_id: str
    result: HistoricalExecutionProjection | None
    error: dict[str, Any] | None


class EvaluateStrategyRangeBatch:
    def __init__(
        self,
        evaluator: EvaluateStrategyRange,
        market_data: MarketDataPort,
        *,
        memo_enabled: bool = True,
    ) -> None:
        """`memo_enabled` is the batch-computation-reuse memo toggle
        (design.md D3): the same evaluator code runs either way; off, the
        evaluation context never retains a result, so every node computes."""

        self._evaluator = evaluator
        self._market_data = market_data
        self._memo_enabled = memo_enabled

    def execute(self, request: StrategyRangeBatchRequest) -> Iterator[BatchVariantOutcome]:
        ids = [variant.variant_id for variant in request.variants]
        if not ids or len(ids) != len(set(ids)):
            raise InvalidRequestError("batch variants must be non-empty with unique variant_id")
        # batch-market-dataset-reuse: this call now owns the shared
        # acquisition, so it must validate the batch range itself rather
        # than relying on a downstream layer (HTTP adapter, MarketDataPort
        # implementation) to be the only place this is ever checked.
        request.time_range.validate_alignment(request.market.base_timeframe)
        # Acquire the shared market dataset exactly once, outside and
        # before the variant loop -- and, per I8's streaming cutover,
        # before the generator below is ever iterated, so a terminal
        # failure here is a normal, whole-request exception (design.md
        # Decision 2), never something that can happen after streaming has
        # already started. Same fail-closed provenance contract as
        # single-range evaluation: when the caller supplies
        # expected_market_data_hash, the shared acquisition is verified
        # against it, not trusted unconditionally.
        market_frame = self._market_data.load_range(
            request.market,
            request.time_range,
            expected_market_data_hash=request.expected_market_data_hash,
        )
        # batch-computation-reuse group 2 (design.md D4) + group 4 (D1/D2):
        # one evaluation context per range-batch call, owning the shared
        # float64/DatetimeIndex/time_ms view of the range and the identity
        # memo, scoped to this exact market frame. Building it does no
        # conversion or computation yet (the arrays are derived lazily, on
        # first use by the first variant that needs them), so nothing
        # observable moves ahead of streaming.
        context = EvaluationContext(market_frame, memo_enabled=self._memo_enabled)
        return self._stream_variants(request, market_frame, context)

    def _stream_variants(
        self,
        request: StrategyRangeBatchRequest,
        market_frame: MarketFrame,
        context: EvaluationContext,
    ) -> Iterator[BatchVariantOutcome]:
        """A generator function's body does not run until iterated --
        `execute()` above returns this call's (not-yet-started) generator
        object only after shared acquisition already completed, so nothing
        here can execute before that point."""

        # design.md D5: every root's memo consumptions are predicted (feature
        # planning + identity resolution only -- no node is computed) before
        # the first root is evaluated, so each memoized result is evicted
        # the moment its last consumer has read it. Prediction never raises.
        context.plan_roots(
            self._evaluator.resolve_memoized_identities(variant.strategy, request.market)
            for variant in request.variants
        )
        for index, variant in enumerate(request.variants):
            try:
                # `root()` only scopes refcount bookkeeping: it never catches,
                # replaces or reorders an exception, so the catch boundary
                # below (and propagation of anything else) is unchanged.
                with context.root(index):
                    result = self._evaluator.execute_projection(
                        StrategyRangeRequest(
                            strategy=variant.strategy,
                            market=request.market,
                            time_range=request.time_range,
                            options=request.options,
                            market_frame=market_frame,
                            market_arrays=context.market_arrays,
                            evaluation_context=context,
                            expected_market_data_hash=request.expected_market_data_hash,
                        )
                    )
                yield BatchVariantOutcome(variant.variant_id, result, None)
            except StrategyEngineError as exc:
                yield BatchVariantOutcome(
                    variant.variant_id,
                    None,
                    {"error": exc.code, "message": exc.message, "details": exc.details},
                )
