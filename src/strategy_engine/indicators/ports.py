"""Indicator implementation ports."""

from __future__ import annotations

from typing import Any, Protocol

from strategy_engine.domain.market import MarketFrame
from strategy_engine.indicators.contracts import (
    FeatureFrame,
    IndicatorPlan,
    NativeFeatureFrame,
    PlannedFeature,
)


class IndicatorEvaluator(Protocol):
    def evaluate(self, market_frame: MarketFrame, plan: IndicatorPlan) -> FeatureFrame: ...

    def evaluate_native(
        self, market_frame: MarketFrame, plan: IndicatorPlan
    ) -> NativeFeatureFrame: ...


class IndicatorRegistryPort(Protocol):
    def list_definitions(self) -> tuple[dict[str, Any], ...]: ...

    def get_schema(self, indicator_id: str) -> dict[str, Any] | None: ...

    def validate_feature(self, feature: PlannedFeature) -> None: ...

    def evaluator(self) -> IndicatorEvaluator | None: ...
