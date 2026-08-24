"""Pure, no-IO bounded live history-start planning.

Generic only: this package and everything under it MUST NOT import any
concrete strategy-family package (e.g. strategy_engine.strategies.ema_pullback)
-- see StrategyHistoryRequirements in contracts.py for the abstraction that
keeps that boundary, and tests/test_live_calculation_architecture.py for the
regression test enforcing it. A concrete strategy family's resolver module
may import from this package (one-directional dependency); this package must
never import back.
"""

from __future__ import annotations

from strategy_engine.strategies.live_calculation.contracts import (
    HistoryRequirement,
    PlannedHistoryStart,
    StrategyHistoryRequirements,
)
from strategy_engine.strategies.live_calculation.indicator_requirements import (
    ResolveIndicatorHistoryRequirements,
)
from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart

__all__ = [
    "HistoryRequirement",
    "PlanLiveHistoryStart",
    "PlannedHistoryStart",
    "ResolveIndicatorHistoryRequirements",
    "StrategyHistoryRequirements",
]
