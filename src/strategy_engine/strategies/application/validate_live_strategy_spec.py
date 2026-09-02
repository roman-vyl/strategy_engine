"""Validation for Runtime-facing live strategy inputs."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError, UnknownResourceError
from strategy_engine.strategies.application.build_live_strategy_feature_plan import (
    BuildLiveStrategyFeaturePlan,
)
from strategy_engine.strategies.application.check_static_semantics import (
    CheckStrategyStaticSemantics,
)
from strategy_engine.strategies.contracts import LiveStrategySpec
from strategy_engine.strategies.ports import StrategyRegistryPort


class ValidateLiveStrategySpec:
    def __init__(
        self,
        registry: StrategyRegistryPort,
        feature_plan_builder: BuildLiveStrategyFeaturePlan,
        static_semantics_checker: CheckStrategyStaticSemantics | None = None,
    ) -> None:
        self._registry = registry
        self._feature_plan_builder = feature_plan_builder
        self._static_semantics_checker = static_semantics_checker

    def execute(self, strategy: LiveStrategySpec) -> None:
        if not strategy.strategy_id:
            raise InvalidRequestError("strategy_id is required")
        known = {item["strategy_id"] for item in self._registry.list_definitions()}
        if strategy.strategy_id not in known:
            raise UnknownResourceError("unknown strategy", strategy_id=strategy.strategy_id)
        if self._static_semantics_checker is not None:
            self._static_semantics_checker.execute(strategy)
        self._feature_plan_builder.execute(strategy)
