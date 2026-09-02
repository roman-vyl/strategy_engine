"""Canonical strategy-input and currently ported semantic validation."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError, UnknownResourceError
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.check_static_semantics import (
    CheckStrategyStaticSemantics,
)
from strategy_engine.strategies.contracts import LiveStrategySpec, strategy_config_hash
from strategy_engine.strategies.ports import StrategyRegistryPort


class ValidateStrategySpec:
    def __init__(
        self,
        registry: StrategyRegistryPort,
        feature_plan_builder: BuildStrategyFeaturePlan | None = None,
        static_semantics_checker: CheckStrategyStaticSemantics | None = None,
    ) -> None:
        self._registry = registry
        self._feature_plan_builder = feature_plan_builder
        self._static_semantics_checker = static_semantics_checker

    def execute(self, strategy: LiveStrategySpec) -> str:
        if not strategy.strategy_id:
            raise InvalidRequestError("strategy_id is required")
        known = {item["strategy_id"] for item in self._registry.list_definitions()}
        if strategy.strategy_id not in known:
            raise UnknownResourceError("unknown strategy", strategy_id=strategy.strategy_id)
        if self._feature_plan_builder is None:
            from strategy_engine.domain.errors import UnsupportedCapabilityError

            raise UnsupportedCapabilityError(f"strategy:{strategy.strategy_id}")
        if self._static_semantics_checker is not None:
            self._static_semantics_checker.execute(strategy)
        self._feature_plan_builder.execute(strategy)
        return strategy_config_hash(strategy)
