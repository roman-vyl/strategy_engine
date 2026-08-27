"""Strategy evaluation envelopes and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from strategy_engine.domain.market import MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.values import canonical_json_hash


@dataclass(frozen=True, slots=True)
class LiveStrategySpec:
    """The one canonical strategy input for every evaluation/validation
    boundary — live and historical alike. No strategy_version, no
    caller-supplied instance_id, no compatibility_profile: none of the
    three carried real calculation semantics (strategy-evaluation-
    canonical-boundary-v1)."""

    strategy_id: str
    raw_spec: dict[str, Any]


def strategy_config_hash(strategy: LiveStrategySpec) -> str:
    """Provenance hash over the canonical strategy input only.

    Deliberately a standalone function, not a `LiveStrategySpec`
    property: this type is also used by /live-entry and /open-trade,
    whose own specs forbid exposing config-hash/provenance in their
    responses. A property would be one habit away from leaking there;
    a function called explicitly only from validation/range call sites
    keeps that boundary honest by construction.
    """

    return canonical_json_hash(
        {
            "strategy_id": strategy.strategy_id,
            "raw_spec": strategy.raw_spec,
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
    strategy: LiveStrategySpec
    market: MarketStream
    time_range: TimeRange
    expected_market_data_hash: str | None = None
    options: StrategyOutputOptions = field(default_factory=StrategyOutputOptions)
    # Internal-only seam (batch-market-dataset-reuse): when set, this exact
    # already-acquired MarketFrame is used instead of fetching one, so a
    # batch caller can share one acquisition across variants. Not exposed on
    # any HTTP request DTO; absent (None) preserves today's fetch-per-call
    # behavior exactly.
    market_frame: MarketFrame | None = None


@dataclass(frozen=True, slots=True)
class StrategyRangeResult:
    strategy_id: str
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
    strategy: LiveStrategySpec


@dataclass(frozen=True, slots=True)
class StrategyRangeBatchRequest:
    market: MarketStream
    time_range: TimeRange
    variants: tuple[StrategyBatchVariant, ...]
    options: StrategyOutputOptions = field(default_factory=StrategyOutputOptions)


@dataclass(frozen=True, slots=True)
class ManagedReplayRequest:
    strategy: LiveStrategySpec
    market: MarketStream
    time_range: TimeRange
    trade_id: str
    side: Literal["long", "short"]
    entry_time_ms: int
    entry_price: float


@dataclass(frozen=True, slots=True)
class LiveEntryProjectionRequest:
    strategy: LiveStrategySpec
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
class DesiredEntry:
    side: str
    source_plan_bar_open_time_ms: int
    planned_entry_price: str
    initial_stop_price: str
    initial_take_price: str
    locked_exit_profile: str


@dataclass(frozen=True, slots=True)
class LiveEntryProjectionResult:
    desired_entry: DesiredEntry | None


@dataclass(frozen=True, slots=True)
class ExecutedTradeReceipt:
    side: str
    source_plan_bar_open_time_ms: int
    entry_bar_open_time_ms: int
    planned_entry_price: str
    initial_stop_price: str
    initial_take_price: str
    locked_exit_profile: str


@dataclass(frozen=True, slots=True)
class OpenTradeProjectionRequest:
    strategy: LiveStrategySpec
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
    desired_protection: DesiredProtection
    close_signal: StrategicCloseSignal
    diagnostics: OpenTradeDiagnostics
