"""Shared pipeline helpers for strategy-level context."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.spec import EmaPullbackStrategySpec


def build_context_bundle_for_spec(
    spec: EmaPullbackStrategySpec,
    df: pd.DataFrame,
    plan: FeaturePlan,
) -> ContextBundle | None:
    """Build context bundle once per enriched dataframe when contexts are declared."""

    if not spec.contexts:
        return None
    return ContextBundle.build(spec, df, plan)


def require_context_bundle(
    spec: EmaPullbackStrategySpec,
    context_bundle: ContextBundle | None,
) -> ContextBundle | None:
    if not spec.contexts:
        return None
    if context_bundle is None:
        raise ValueError(
            "context_bundle is required when strategy.contexts is non-empty; "
            "build it once after feature enrichment and pass to signals and exits"
        )
    return context_bundle
