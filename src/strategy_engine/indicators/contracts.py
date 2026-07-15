"""Indicator plan and feature-frame contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.validity import Validity
from strategy_engine.domain.values import canonical_json_hash


@dataclass(frozen=True, slots=True)
class PlannedFeature:
    output_id: str
    kind: str
    timeframe: str
    source: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "kind": self.kind,
            "timeframe": self.timeframe,
            "source": self.source,
            "parameters": self.parameters,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class IndicatorPlan:
    plan_version: str
    features: tuple[PlannedFeature, ...]

    @property
    def plan_hash(self) -> str:
        return canonical_json_hash(
            {
                "plan_version": self.plan_version,
                "features": [feature.canonical_payload() for feature in self.features],
            }
        )


@dataclass(frozen=True, slots=True)
class IndicatorRangeRequest:
    market: MarketStream
    time_range: TimeRange
    plan: IndicatorPlan
    expected_market_data_hash: str | None = None


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    market: MarketStream
    requested_range: TimeRange
    time_ms: tuple[int, ...]
    series: dict[str, tuple[str | None, ...]]
    validity: dict[str, Validity]
    plan_hash: str
    market_data_hash: str
    market_bars: tuple[MarketBar, ...] = ()
