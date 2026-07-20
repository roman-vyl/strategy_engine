"""Internal EMA Pullback live projection results."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_engine.strategies.contracts import LiveEntryPlan


@dataclass(frozen=True, slots=True)
class EmaPullbackLiveEntryProjection:
    plans_by_side: dict[str, LiveEntryPlan | None]


@dataclass(frozen=True, slots=True)
class EmaPullbackDesiredProtection:
    stop_price: str
    take_price: str | None


@dataclass(frozen=True, slots=True)
class EmaPullbackCloseSignal:
    active: bool
    reason: str | None
    component_id: str | None
    layer: str | None


@dataclass(frozen=True, slots=True)
class EmaPullbackOpenTradeDiagnostics:
    phase: str
    max_phase_reached: str
    bars_in_trade: int
    mfe_pct: str
    mae_pct: str
    managed_events: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class EmaPullbackOpenTradeProjection:
    desired_protection: EmaPullbackDesiredProtection
    close_signal: EmaPullbackCloseSignal
    diagnostics: EmaPullbackOpenTradeDiagnostics
