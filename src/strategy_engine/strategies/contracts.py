"""Strategy evaluation envelopes and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.values import canonical_json_hash


@dataclass(frozen=True, slots=True)
class StrategySpecEnvelope:
    strategy_id: str
    strategy_version: str
    instance_id: str
    raw_spec: dict[str, Any]
    compatibility_profile: str = "bbb_v1"

    @property
    def config_hash(self) -> str:
        return canonical_json_hash(
            {
                "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version,
                "raw_spec": self.raw_spec,
                "compatibility_profile": self.compatibility_profile,
            }
        )


@dataclass(frozen=True, slots=True)
class StrategyOutputOptions:
    include_features: bool = True
    include_contexts: bool = True
    include_component_evidence: bool = True
    include_state_artifact: bool = False


@dataclass(frozen=True, slots=True)
class StrategyRangeRequest:
    strategy: StrategySpecEnvelope
    market: MarketStream
    time_range: TimeRange
    expected_market_data_hash: str | None = None
    options: StrategyOutputOptions = field(default_factory=StrategyOutputOptions)


@dataclass(frozen=True, slots=True)
class StrategyRangeResult:
    strategy_id: str
    strategy_version: str
    instance_id: str
    config_hash: str
    market: MarketStream
    requested_range: TimeRange
    features: dict[str, Any]
    contexts: dict[str, Any]
    entries: dict[str, Any]
    exit_policy: dict[str, Any]
    component_evidence: dict[str, Any]
    validity: dict[str, Any]
    state_artifact: dict[str, Any] | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StrategyBatchVariant:
    variant_id: str
    strategy: StrategySpecEnvelope


@dataclass(frozen=True, slots=True)
class StrategyRangeBatchRequest:
    market: MarketStream
    time_range: TimeRange
    variants: tuple[StrategyBatchVariant, ...]
    options: StrategyOutputOptions = field(default_factory=StrategyOutputOptions)


@dataclass(frozen=True, slots=True)
class ManagedReplayRequest:
    strategy: StrategySpecEnvelope
    market: MarketStream
    time_range: TimeRange
    trade_id: str
    side: str
    entry_time_ms: int
    entry_price: float
