"""EMA pullback strategy semantic modules."""

from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
    build_feature_plan_from_canonical_spec,
)

__all__ = ["EmaPullbackFeaturePlan", "build_feature_plan_from_canonical_spec"]
