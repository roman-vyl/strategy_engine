"""EMA Pullback implementations of the Live Projections boundary."""

from strategy_engine.strategies.ema_pullback.live_projections.live_entry import (
    EmaPullbackLiveEntryProjectionAdapter,
)
from strategy_engine.strategies.ema_pullback.live_projections.open_trade import (
    EmaPullbackOpenTradeProjectionAdapter,
)

__all__ = [
    "EmaPullbackLiveEntryProjectionAdapter",
    "EmaPullbackOpenTradeProjectionAdapter",
]
