"""Typed result contracts for ema_pullback execution modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoadedCandles:
    """OHLCV frame plus candle range metadata needed by reports/artifacts."""

    ohlcv: Any
    candles_count: int
    from_open_time_ms: int
    to_open_time_ms: int


@dataclass(frozen=True)
class SideMetrics:
    trades: int
    pnl: float
    return_pct: float
    profit_factor: float | None
    win_rate: float | None

    def to_payload(self) -> dict[str, int | float | None]:
        return {
            "trades": self.trades,
            "pnl": self.pnl,
            "return_pct": self.return_pct,
            "profit_factor": self.profit_factor,
            "win_rate": self.win_rate,
        }


@dataclass(frozen=True)
class OpenTradesBreakdown:
    """Counts of open (not yet closed) positions by side; separate from realized metrics."""

    long: int
    short: int
    total: int

    def to_payload(self) -> dict[str, int]:
        return {"long": self.long, "short": self.short, "total": self.total}


@dataclass(frozen=True)
class VariantMetrics:
    long: SideMetrics
    short: SideMetrics
    total: SideMetrics
    sharpe: float
    max_drawdown: float
    open_trades: OpenTradesBreakdown
    profile_breakdown: dict[str, Any] | None = None
    profile_side_breakdown: dict[str, Any] | None = None
    exit_reason_breakdown: dict[str, Any] | None = None
    fee_diagnostics: dict[str, Any] | None = None
    bounce_counter_breakdown: dict[str, Any] | None = None
    quality_flag_breakdown: dict[str, Any] | None = None
    exit_component_quality_breakdown: dict[str, Any] | None = None
    path_diagnostics_summary: dict[str, Any] | None = None
    trade_management_summary: dict[str, Any] | None = None
    baseline_vs_managed_summary: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        total_payload = self.total.to_payload()
        total_payload["sharpe"] = self.sharpe
        total_payload["max_drawdown"] = self.max_drawdown
        payload: dict[str, Any] = {
            "long": self.long.to_payload(),
            "short": self.short.to_payload(),
            "total": total_payload,
            "open_trades": self.open_trades.to_payload(),
        }
        if self.profile_breakdown is not None:
            payload["profile_breakdown"] = self.profile_breakdown
        if self.profile_side_breakdown is not None:
            payload["profile_side_breakdown"] = self.profile_side_breakdown
        if self.exit_reason_breakdown is not None:
            payload["exit_reason_breakdown"] = self.exit_reason_breakdown
        if self.fee_diagnostics is not None:
            payload["fee_diagnostics"] = self.fee_diagnostics
        if self.bounce_counter_breakdown is not None:
            payload["bounce_counter_breakdown"] = self.bounce_counter_breakdown
        if self.quality_flag_breakdown is not None:
            payload["quality_flag_breakdown"] = self.quality_flag_breakdown
        if self.exit_component_quality_breakdown is not None:
            payload["exit_component_quality_breakdown"] = self.exit_component_quality_breakdown
        if self.path_diagnostics_summary is not None:
            payload["path_diagnostics_summary"] = self.path_diagnostics_summary
        if self.trade_management_summary is not None:
            payload["trade_management_summary"] = self.trade_management_summary
        if self.baseline_vs_managed_summary is not None:
            payload["baseline_vs_managed_summary"] = self.baseline_vs_managed_summary
        return payload


@dataclass(frozen=True)
class VariantResult:
    variant: str
    config_id: str
    symbol: str
    timeframe: str
    strategy_spec: dict[str, Any]
    metrics: VariantMetrics
    component_counters: list[dict[str, Any]]
    trade_records: list[dict[str, Any]]
    trade_management_events: list[dict[str, Any]] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "variant": self.variant,
            "config_id": self.config_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_spec": self.strategy_spec,
            "metrics": self.metrics.to_payload(),
            "component_counters": self.component_counters,
            "trade_records": self.trade_records,
        }
        if self.trade_management_events is not None:
            payload["trade_management_events"] = self.trade_management_events
        return payload
