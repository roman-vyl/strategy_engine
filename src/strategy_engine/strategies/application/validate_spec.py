"""Strategy-envelope and currently ported semantic validation."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError, UnknownResourceError
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import StrategySpecEnvelope
from strategy_engine.strategies.ports import StrategyRegistryPort


class ValidateStrategySpec:
    def __init__(
        self,
        registry: StrategyRegistryPort,
        feature_plan_builder: BuildStrategyFeaturePlan | None = None,
    ) -> None:
        self._registry = registry
        self._feature_plan_builder = feature_plan_builder

    def execute(self, strategy: StrategySpecEnvelope) -> str:
        if not strategy.strategy_id or not strategy.strategy_version or not strategy.instance_id:
            raise InvalidRequestError("strategy_id, strategy_version, and instance_id are required")
        known = {item["strategy_id"] for item in self._registry.list_definitions()}
        if strategy.strategy_id not in known:
            raise UnknownResourceError("unknown strategy", strategy_id=strategy.strategy_id)
        if self._feature_plan_builder is None:
            from strategy_engine.domain.errors import UnsupportedCapabilityError

            raise UnsupportedCapabilityError(f"strategy:{strategy.strategy_id}")
        self._feature_plan_builder.execute(strategy)
        return strategy.config_hash
