"""Strategy evaluation envelopes and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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
    potential_entries: dict[str, Any]
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
    side: Literal["long", "short"]
    entry_time_ms: int
    entry_price: float


@dataclass(frozen=True, slots=True)
class LiveEntryProjectionRequest:
    strategy: StrategySpecEnvelope
    market: MarketStream
    target_bar_open_time_ms: int


@dataclass(frozen=True, slots=True)
class LiveEntryPlan:
    side: str
    source_plan_bar_open_time_ms: int
    planned_entry_price: str
    initial_stop_price: str
    initial_take_price: str
    locked_exit_profile: str


@dataclass(frozen=True, slots=True)
class LiveEntryProjectionResult:
    strategy_id: str
    strategy_version: str
    instance_id: str
    source_config_hash: str
    market: MarketStream
    target_bar_open_time_ms: int
    plans_by_side: dict[str, LiveEntryPlan | None]


@dataclass(frozen=True, slots=True)
class ExecutedTradeReceipt:
    trade_id: str
    instance_id: str
    strategy_id: str
    strategy_version: str
    source_config_hash: str
    ticker: str
    base_timeframe: str
    side: str
    source_plan_bar_open_time_ms: int
    entry_bar_open_time_ms: int
    planned_entry_price: str
    executed_entry_price: str
    initial_stop_price: str
    initial_take_price: str
    locked_exit_profile: str
    abi_entry_correlation: str


@dataclass(frozen=True, slots=True)
class OpenTradeProjectionRequest:
    strategy: StrategySpecEnvelope
    market: MarketStream
    target_bar_open_time_ms: int
    executed_trade_receipt: ExecutedTradeReceipt


@dataclass(frozen=True, slots=True)
class DesiredProtection:
    stop_price: str
    take_price: str | None


@dataclass(frozen=True, slots=True)
class StrategicCloseSignal:
    active: bool
    reason: str | None
    component_id: str | None
    layer: str | None


@dataclass(frozen=True, slots=True)
class OpenTradeDiagnostics:
    phase: str
    max_phase_reached: str
    bars_in_trade: int
    mfe_pct: str
    mae_pct: str
    managed_events: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class OpenTradeProjectionResult:
    trade_id: str
    instance_id: str
    strategy_id: str
    strategy_version: str
    source_config_hash: str
    market: MarketStream
    target_bar_open_time_ms: int
    desired_protection: DesiredProtection
    close_signal: StrategicCloseSignal
    diagnostics: OpenTradeDiagnostics
