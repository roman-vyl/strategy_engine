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
