"""Strategy catalog query service."""

from __future__ import annotations

from typing import Any

from strategy_engine.domain.errors import UnknownResourceError
from strategy_engine.strategies.ports import StrategyRegistryPort


class StrategyCatalog:
    def __init__(self, registry: StrategyRegistryPort) -> None:
        self._registry = registry

    def list(self) -> tuple[dict[str, Any], ...]:
        return self._registry.list_definitions()

    def schema(self, strategy_id: str) -> dict[str, Any]:
        schema = self._registry.get_schema(strategy_id)
        if schema is None:
            raise UnknownResourceError("unknown strategy", strategy_id=strategy_id)
        return schema
