"""Concrete capability registries."""

from __future__ import annotations

from typing import Any, cast

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.feature_kinds import feature_kinds, find_feature_kind
from strategy_engine.indicators.implementations import RangeIndicatorEvaluator
from strategy_engine.indicators.ports import IndicatorEvaluator
from strategy_engine.strategies.ports import StrategyEvaluator


class IndicatorRegistry:
    """Public indicator capabilities, delegated to the canonical feature-kind
    contract (`indicators/feature_kinds.py`, design D13)."""

    def __init__(self) -> None:
        self._evaluator = RangeIndicatorEvaluator()

    def list_definitions(self) -> tuple[dict[str, Any], ...]:
        return tuple(cast(dict[str, Any], contract.schema) for contract in feature_kinds())

    def get_schema(self, indicator_id: str) -> dict[str, Any] | None:
        contract = find_feature_kind(indicator_id)
        return None if contract is None else cast(dict[str, Any], contract.schema)

    def validate_feature(self, feature: PlannedFeature) -> None:
        contract = find_feature_kind(feature.kind)
        if contract is None:
            raise UnsupportedCapabilityError(
                f"indicator:{feature.kind}",
                f"Indicator implementation is not ported: {feature.kind}",
            )
        contract.validate(feature)

    def evaluator(self) -> IndicatorEvaluator:
        return self._evaluator


_EMA_PULLBACK_SCHEMA: dict[str, Any] = {
    "strategy_id": "ema_pullback",
    "title": "EMA Pullback",
    "accepted_spec_shape": "strategy_spec_to_dict",
    "supports_feature_planning": True,
    "supports_range_evaluation": True,
    "evaluation_stage": "decisions_ready",
    "supports_contexts": True,
    "supports_decisions": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
}


class StrategyRegistry:
    def __init__(self, ema_pullback_evaluator: StrategyEvaluator | None = None) -> None:
        self._ema_pullback_evaluator = ema_pullback_evaluator

    def list_definitions(self) -> tuple[dict[str, Any], ...]:
        return (_EMA_PULLBACK_SCHEMA,)

    def get_schema(self, strategy_id: str) -> dict[str, Any] | None:
        if strategy_id == "ema_pullback":
            return _EMA_PULLBACK_SCHEMA
        return None

    def evaluator(self, strategy_id: str) -> StrategyEvaluator | None:
        if strategy_id == "ema_pullback":
            return self._ema_pullback_evaluator
        return None


class EmptyStrategyRegistry:
    """Backward-compatible test registry with no strategy capabilities."""

    def list_definitions(self) -> tuple[dict[str, Any], ...]:
        return ()

    def get_schema(self, strategy_id: str) -> dict[str, Any] | None:
        return None

    def evaluator(self, strategy_id: str) -> StrategyEvaluator | None:
        return None
