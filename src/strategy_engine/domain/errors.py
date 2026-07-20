"""Stable application errors shared across adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StrategyEngineError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


class InvalidRequestError(StrategyEngineError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("invalid_request", message, details, 422)


class UnknownResourceError(StrategyEngineError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("unknown_resource", message, details, 404)


class UnsupportedCapabilityError(StrategyEngineError):
    def __init__(self, capability: str, message: str | None = None) -> None:
        super().__init__(
            "unsupported_capability",
            message or f"Capability is not implemented: {capability}",
            {"capability": capability},
            501,
        )


class MarketDataUnavailableError(StrategyEngineError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("market_data_unavailable", message, details, 503)


class UpstreamContractError(StrategyEngineError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("upstream_contract_error", message, details, 502)


class MarketStreamNotReadyError(StrategyEngineError):
    def __init__(self, message: str = "Market stream is not ready", **details: Any) -> None:
        super().__init__("market_stream_not_ready", message, details, 409)


class TargetBarNotCommittedError(StrategyEngineError):
    def __init__(self, message: str = "Target bar is not committed", **details: Any) -> None:
        super().__init__("target_bar_not_committed", message, details, 409)


class TradeContractMismatchError(StrategyEngineError):
    def __init__(
        self, message: str = "Trade contract does not match request", **details: Any
    ) -> None:
        super().__init__("trade_contract_mismatch", message, details, 409)


class TradeHistoryUnavailableError(StrategyEngineError):
    def __init__(self, message: str = "Trade history is unavailable", **details: Any) -> None:
        super().__init__("trade_history_unavailable", message, details, 409)
