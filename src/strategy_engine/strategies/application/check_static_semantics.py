"""Strategy-dispatched static semantic check (authoritative, market-data-free)."""

from __future__ import annotations

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.contracts import LiveStrategySpec
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)


class CheckStrategyStaticSemantics:
    def execute(self, strategy: LiveStrategySpec) -> None:
        if strategy.strategy_id != "ema_pullback":
            raise UnsupportedCapabilityError(f"strategy_static_semantics:{strategy.strategy_id}")
        check_ema_pullback_static_semantics(strategy.raw_spec)
