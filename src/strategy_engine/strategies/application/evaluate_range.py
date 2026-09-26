"""Strategy range evaluation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.evaluation_context import EvaluationContext
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import (
    HistoricalExecutionProjection,
    LiveStrategySpec,
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
        return self._evaluate_root(evaluator, request, evaluator.evaluate_execution_projection)

    def execute_diagnostics(self, request: StrategyRangeRequest) -> StrategyDiagnosticEvaluation:
        evaluator = self._prepare(request)
        return self._evaluate_root(evaluator, request, evaluator.evaluate_diagnostics)

    def _evaluate_root[R](
        self,
        evaluator: StrategyEvaluator,
        request: StrategyRangeRequest,
        evaluate: Callable[[StrategyRangeRequest], R],
    ) -> R:
        """Evaluate `request` as one root of an `EvaluationContext`
        (batch-computation-reuse, design.md D1/D4, tasks 2.4/5.2: one
        evaluation path, single-spec = a context with one root, range-batch
        = a context with N roots).

        A request already carrying a context is a root of a caller-owned
        context -- `EvaluateStrategyRangeBatch` built it, planned all N
        roots and scopes this root -- and is evaluated as is. Otherwise this
        is a single-spec request: the market frame is acquired exactly as
        evaluation acquired it before (same validation, same `load_range`
        call, same failure precedence), and the request becomes the only
        root of a context over that frame, planned and scoped through the
        same `plan_roots()` / `root()` the batch uses."""

        if request.evaluation_context is not None:
            return evaluate(request)
        market_frame = evaluator.load_market_frame(request)
        context = EvaluationContext(market_frame, request.market_arrays)
        context.plan_roots([self.resolve_memoized_identities(request.strategy, request.market)])
        with context.root(0):
            return evaluate(
                replace(
                    request,
                    market_frame=market_frame,
                    market_arrays=context.market_arrays,
                    evaluation_context=context,
                )
            )

    def resolve_memoized_identities(
        self, strategy: LiveStrategySpec, market: MarketStream
    ) -> tuple[NodeSpec, ...]:
        """Predicted memo consumptions of one context root, for the refcount
        pre-pass (`plan_roots`) of both the range-batch and the single-spec
        context (batch-computation-reuse, design.md D5).

        Pure prediction: never raises and never runs validation or
        evaluation. A strategy whose evaluator does not take part in
        memoization, or whose prediction fails (its real evaluation will
        then fail at its own point, as before), predicts nothing. A wrong
        prediction can only affect retention, never a result."""

        try:
            evaluator = self._registry.evaluator(strategy.strategy_id)
            resolver = getattr(evaluator, "resolve_memoized_identities", None)
            if resolver is None:
                return ()
            return tuple(resolver(strategy, base_timeframe=market.base_timeframe))
        except Exception:
            return ()

    def _prepare(self, request: StrategyRangeRequest) -> StrategyEvaluator:
        request.time_range.validate_alignment(request.market.base_timeframe)
        evaluator = self._registry.evaluator(request.strategy.strategy_id)
        if evaluator is None:
            raise UnsupportedCapabilityError(f"strategy:{request.strategy.strategy_id}")
        self._validator.execute(request.strategy)
        return evaluator
