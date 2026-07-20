"""Strategy-family Live Projections extension boundary."""

from strategy_engine.strategies.live_projections.contracts import (
    LiveEntryProjectionAdapter,
    OpenTradeProjectionAdapter,
)
from strategy_engine.strategies.live_projections.registry import (
    LiveEntryProjectionRegistry,
    OpenTradeProjectionRegistry,
)

__all__ = [
    "LiveEntryProjectionAdapter",
    "LiveEntryProjectionRegistry",
    "OpenTradeProjectionAdapter",
    "OpenTradeProjectionRegistry",
]
