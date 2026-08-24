"""Contracts for bounded live history-start planning. No MDS/pandas/HTTP here."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class HistoryRequirement:
    """One component's declared history need, on its own bar axis.

    ``timeframe`` is the axis the requirement is expressed on: an indicator
    kind/period pair for indicator warm-up, or the base FeatureFrame axis for
    strategy-semantic lookback (see whichever strategy-family resolver
    implements StrategyHistoryRequirements below).
    """

    timeframe: str
    bars: int
    reason: str


class StrategyHistoryRequirements(Protocol):
    """Boundary abstraction between the generic planning chain and a
    concrete strategy family's own semantic-history knowledge (design.md
    Decision 2/12). PlanLiveHistoryStart depends only on this Protocol --
    never on a specific strategy family package -- so which family backs it
    is a composition-layer decision, not something the generic planner
    hardcodes."""

    def execute(self, raw_spec: Mapping[str, Any]) -> tuple[HistoryRequirement, ...]: ...


@dataclass(frozen=True, slots=True)
class PlannedHistoryStart:
    """Result of PlanLiveHistoryStart. Two winning-requirement fields, not one:

    from_ms is jointly driven by the largest indicator-warm-up span and the
    largest strategy-semantic span (they are summed, not maxed), so a single
    combined field cannot represent "the" reason from_ms landed where it did.
    """

    from_ms: int
    winning_indicator_requirement: HistoryRequirement
    winning_strategy_requirement: HistoryRequirement
    requirements: tuple[HistoryRequirement, ...]
