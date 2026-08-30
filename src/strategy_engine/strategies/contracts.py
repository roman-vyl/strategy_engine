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
class DecisionEntry:
    """One side's entry condition firing at a bar, with the SL/TP ratio
    values relevant to that entry only -- Research reads these exactly
    once, at the entry bar, per `compact-strategy-evaluation-boundary-v1`
    (proven from `protection.py::resolve_initial_protection`: the ratio
    series is never re-read after entry)."""

    side: Literal["long", "short"]
    stop_loss_ratio: float | None
    take_profit_ratio: float | None


@dataclass(frozen=True, slots=True)
class DecisionSignalExit:
    long: bool
    short: bool


@dataclass(frozen=True, slots=True)
class DecisionStopReady:
    long: bool
    short: bool


@dataclass(frozen=True, slots=True)
class StrategyDecisionEvent:
    """One bar carrying at least one of entry/signal_exit/stop_ready.
    Bars with none of these are not represented at all -- the sparse
    contract is O(events), not O(bar_count)
    (`strategy-research-execution-contract-v1`)."""

    bar_index: int
    entry: DecisionEntry | None = None
    signal_exit: DecisionSignalExit | None = None
    stop_ready: DecisionStopReady | None = None


@dataclass(frozen=True, slots=True)
class StrategyEvaluationExecution:
    """The mandatory execution contract: identity, provenance, and sparse
    decision events only. No `time_ms` (bar_index + market_data_hash +
    bar_count is the join key back to Research's own MarketFrame -- proven
    redundant, `compact-strategy-evaluation-boundary-v1`). No diagnostic
    data (`features`/`contexts`/`component_evidence`/`potential_entries`)
    -- those live only on `StrategyDiagnosticEvaluation`, produced by a
    separate, explicitly-requested entrypoint."""

    strategy_id: str
    config_hash: str
    market: MarketStream
    requested_range: TimeRange
    market_data_hash: str
    bar_count: int
    decision_events: tuple[StrategyDecisionEvent, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StrategyDiagnosticEvaluation:
    """Dense per-bar diagnostic trace -- produced only by the diagnostic-
    evaluation entrypoint, never as a side effect of an execution-contract
    request. Provenance fields let Research fail closed if this doesn't
    match the run it's meant to explain."""

    strategy_id: str
    config_hash: str
    market: MarketStream
    requested_range: TimeRange
    market_data_hash: str
    bar_count: int
    features: dict[str, Any]
    contexts: dict[str, Any]
    potential_entries: dict[str, Any]
    component_evidence: dict[str, Any]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExitAttribution:
    """Shared attribution shape across every historical execution fact
    (`compact-strategy-evaluation-boundary-v1`, I0 corrective pass).
    Canonical `exit_kind` values: `"stop_loss"` for `initial_stop`,
    `"take_profit"` for `initial_take`, `"signal"` for a signal-exit
    candidate. No `layer` field -- Research derives the canonical
    constant `"exit_policy"`, this is not an independent Engine
    decision."""

    rule_id: str
    component_id: str
    exit_kind: Literal["stop_loss", "take_profit", "signal"]


@dataclass(frozen=True, slots=True)
class InitialProtectionLeg:
    """One resolved, attributed protection leg (stop or take) at an
    entry opportunity's bar. Non-null legs are always fully populated --
    there is no bare ratio without attribution."""

    ratio: float
    attribution: ExitAttribution


@dataclass(frozen=True, slots=True)
class ExecutableEntryOpportunity:
    """`entry_allowed AND protection_ready`, collapsed -- `stop_ready`
    never exists as its own field anywhere in this contract.
    `locked_exit_profile` is the profile active at this bar (the
    candidate lock value if a caller treats this bar as the real entry)
    -- Engine has no trade-lifecycle state and cannot itself prove this
    stays locked across a trade's life; that's a Research Service
    concern. `initial_stop`/`initial_take` are independently nullable --
    a strategy MAY be take-only or stop-only for the active
    always_on+profile combination."""

    bar_index: int
    side: Literal["long", "short"]
    locked_exit_profile: str
    initial_stop: InitialProtectionLeg | None
    initial_take: InitialProtectionLeg | None


@dataclass(frozen=True, slots=True)
class SignalExitCandidate:
    attribution: ExitAttribution


@dataclass(frozen=True, slots=True)
class SignalExitEvent:
    bar_index: int
    candidates: tuple[SignalExitCandidate, ...]


@dataclass(frozen=True, slots=True)
class SignalExitProjection:
    """Per-side, per-profile sparse event lists -- a caller holding a
    locked profile for an open position looks up only that profile's
    own event list for bars after entry, never a flattened
    current-bar-profile series."""

    long: dict[str, tuple[SignalExitEvent, ...]]
    short: dict[str, tuple[SignalExitEvent, ...]]


@dataclass(frozen=True, slots=True)
class HistoricalExecutionProjection:
    """The target mandatory execution contract
    (`compact-strategy-evaluation-boundary-v1`), superseding
    `StrategyEvaluationExecution`/`StrategyDecisionEvent`. Not yet wired
    to any route -- I1 builds this as a pure, additive builder; route
    cutover is I7."""

    strategy_id: str
    config_hash: str
    market: MarketStream
    requested_range: TimeRange
    market_data_hash: str
    bar_count: int
    entry_opportunities: tuple[ExecutableEntryOpportunity, ...]
    signal_exit_events: SignalExitProjection
    warnings: tuple[str, ...]


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
    # Same fail-closed provenance contract as single-range evaluation
    # (StrategyRangeRequest.expected_market_data_hash): when set, the shared
    # L0 market acquisition is verified against it rather than trusted
    # unconditionally.
    expected_market_data_hash: str | None = None


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
