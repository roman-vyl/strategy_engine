"""Indicator catalog query service."""

from __future__ import annotations

from typing import Any

from strategy_engine.domain.errors import UnknownResourceError
from strategy_engine.indicators.ports import IndicatorRegistryPort


class IndicatorCatalog:
    def __init__(self, registry: IndicatorRegistryPort) -> None:
        self._registry = registry

    def list(self) -> tuple[dict[str, Any], ...]:
        return self._registry.list_definitions()

    def schema(self, indicator_id: str) -> dict[str, Any]:
        schema = self._registry.get_schema(indicator_id)
        if schema is None:
            raise UnknownResourceError("unknown indicator", indicator_id=indicator_id)
        return schema
