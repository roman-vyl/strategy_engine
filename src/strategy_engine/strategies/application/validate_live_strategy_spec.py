"""Validation for Runtime-facing live strategy inputs."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError, UnknownResourceError
from strategy_engine.strategies.application.build_live_strategy_feature_plan import (
    BuildLiveStrategyFeaturePlan,
)
from strategy_engine.strategies.contracts import LiveStrategySpec
from strategy_engine.strategies.ports import StrategyRegistryPort


class ValidateLiveStrategySpec:
    def __init__(
        self,
        registry: StrategyRegistryPort,
        feature_plan_builder: BuildLiveStrategyFeaturePlan,
    ) -> None:
        self._registry = registry
        self._feature_plan_builder = feature_plan_builder

    def execute(self, strategy: LiveStrategySpec) -> None:
        if not strategy.strategy_id or not strategy.instance_id:
            raise InvalidRequestError("strategy_id and instance_id are required")
        known = {item["strategy_id"] for item in self._registry.list_definitions()}
        if strategy.strategy_id not in known:
            raise UnknownResourceError("unknown strategy", strategy_id=strategy.strategy_id)
        self._feature_plan_builder.execute(strategy)
