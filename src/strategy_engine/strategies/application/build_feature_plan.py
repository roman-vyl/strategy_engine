"""Build a strategy-owned indicator plan from the strategy specification."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.contracts import StrategySpecEnvelope
from strategy_engine.strategies.ema_pullback import (
    EmaPullbackFeaturePlan,
    build_feature_plan_from_canonical_spec,
)


class BuildStrategyFeaturePlan:
    def execute(self, strategy: StrategySpecEnvelope) -> EmaPullbackFeaturePlan:
        if strategy.strategy_id != "ema_pullback":
            raise UnsupportedCapabilityError(f"strategy_feature_plan:{strategy.strategy_id}")
        if strategy.compatibility_profile != "bbb_v1":
            raise UnsupportedCapabilityError(
                f"strategy_compatibility_profile:{strategy.compatibility_profile}"
            )
        return build_feature_plan_from_canonical_spec(strategy.raw_spec)
