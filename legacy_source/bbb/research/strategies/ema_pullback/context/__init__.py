"""Strategy-level context bundle and consumer policies."""

from research.strategies.ema_pullback.context.bundle import ContextBundle, ContextOutput
from research.strategies.ema_pullback.context.evaluation import (
    ContextConsumptionResult,
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.context.policies import (
    EXIT_PROFILE_BY_HTF_STATE_POLICY,
    HTF_REGIME_GATE_POLICY,
)

__all__ = [
    "ContextBundle",
    "ContextConsumptionResult",
    "ContextOutput",
    "EXIT_PROFILE_BY_HTF_STATE_POLICY",
    "HTF_REGIME_GATE_POLICY",
    "SideAwareEvaluationContext",
    "evaluate_context_consumption",
]
