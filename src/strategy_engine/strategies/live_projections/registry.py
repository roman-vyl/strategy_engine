"""Separate registries for live-entry and confirmed-open projections."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.live_projections.contracts import (
    LiveEntryProjectionAdapter,
    OpenTradeProjectionAdapter,
)


class LiveEntryProjectionRegistry:
    def __init__(self, *adapters: LiveEntryProjectionAdapter) -> None:
        self._adapters = {adapter.strategy_id: adapter for adapter in adapters}

    def resolve(self, strategy_id: str) -> LiveEntryProjectionAdapter:
        try:
            return self._adapters[strategy_id]
        except KeyError as exc:
            raise UnsupportedCapabilityError(f"strategy_live_entry:{strategy_id}") from exc


class OpenTradeProjectionRegistry:
    def __init__(self, *adapters: OpenTradeProjectionAdapter) -> None:
        self._adapters = {adapter.strategy_id: adapter for adapter in adapters}

    def resolve(self, strategy_id: str) -> OpenTradeProjectionAdapter:
        try:
            return self._adapters[strategy_id]
        except KeyError as exc:
            raise UnsupportedCapabilityError(f"strategy_open_trade:{strategy_id}") from exc
