"""Build a live feature plan without Research compatibility selectors."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.contracts import LiveStrategySpec
from strategy_engine.strategies.ema_pullback import (
    EmaPullbackFeaturePlan,
    build_feature_plan_from_canonical_spec,
)


class BuildLiveStrategyFeaturePlan:
    def execute(self, strategy: LiveStrategySpec) -> EmaPullbackFeaturePlan:
        if strategy.strategy_id != "ema_pullback":
            raise UnsupportedCapabilityError(f"strategy_feature_plan:{strategy.strategy_id}")
        return build_feature_plan_from_canonical_spec(strategy.raw_spec)
