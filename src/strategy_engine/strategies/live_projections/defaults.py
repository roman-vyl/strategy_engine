"""Default strategy-family registrations for Engine composition roots."""

from strategy_engine.strategies.ema_pullback.live_projections import (
    EmaPullbackLiveEntryProjectionAdapter,
)
from strategy_engine.strategies.live_projections.registry import (
    LiveEntryProjectionRegistry,
)


def build_live_entry_projection_registry() -> LiveEntryProjectionRegistry:
    return LiveEntryProjectionRegistry(EmaPullbackLiveEntryProjectionAdapter())
