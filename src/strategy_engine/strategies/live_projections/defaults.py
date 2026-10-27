"""Default strategy-family registrations for Engine composition roots."""

from strategy_engine.strategies.contracts import LiveEntryMode
from strategy_engine.strategies.ema_pullback.live_projections import (
    EmaPullbackLiveEntryProjectionAdapter,
    EmaPullbackOpenTradeProjectionAdapter,
)
from strategy_engine.strategies.live_projections.registry import (
    LiveEntryProjectionRegistry,
    OpenTradeProjectionRegistry,
)


def build_live_entry_projection_registry(
    live_entry_mode: LiveEntryMode = "ema_anchor",
) -> LiveEntryProjectionRegistry:
    return LiveEntryProjectionRegistry(
        EmaPullbackLiveEntryProjectionAdapter(live_entry_mode=live_entry_mode)
    )


def build_open_trade_projection_registry() -> OpenTradeProjectionRegistry:
    return OpenTradeProjectionRegistry(EmaPullbackOpenTradeProjectionAdapter())
