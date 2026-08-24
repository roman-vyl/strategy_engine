"""Pure computation of a bounded live history start. No MDS, no pandas, no HTTP.

See openspec/changes/bounded-live-calculation-window for the full design.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.strategies.live_calculation.contracts import (
    HistoryRequirement,
    PlannedHistoryStart,
    StrategyHistoryRequirements,
)
from strategy_engine.strategies.live_calculation.indicator_requirements import (
    ResolveIndicatorHistoryRequirements,
)


def _resolve_timeframe(timeframe: str, base_timeframe: str) -> str:
    return base_timeframe if timeframe == "base" else timeframe


def _span_ms(requirement: HistoryRequirement, base_timeframe: str) -> int:
    resolved = _resolve_timeframe(requirement.timeframe, base_timeframe)
    return requirement.bars * timeframe_duration_ms(resolved)


class PlanLiveHistoryStart:
    """Combine indicator warm-up and strategy-semantic history requirements
    additively (not via max()) into a single bounded from_ms.

    Generic: depends only on StrategyHistoryRequirements (design.md
    Decision 2/12), never on a concrete strategy family package -- which
    family backs strategy_requirements is a composition-layer decision, not
    something this planner hardcodes or defaults to.

    Pure and no-IO: never calls MDS, never reads candles, never imports
    pandas. base_timeframe and history_anchor_open_time_ms are supplied by
    the caller -- this planner never selects the anchor itself.
    """

    def __init__(
        self,
        *,
        strategy_requirements: StrategyHistoryRequirements,
        indicator_requirements: ResolveIndicatorHistoryRequirements | None = None,
    ) -> None:
        self._indicator_requirements = (
            indicator_requirements or ResolveIndicatorHistoryRequirements()
        )
        self._strategy_requirements = strategy_requirements

    def execute(
        self,
        *,
        raw_spec: Mapping[str, Any],
        indicator_plan: IndicatorPlan,
        base_timeframe: str,
        history_anchor_open_time_ms: int,
    ) -> PlannedHistoryStart:
        indicator_reqs = self._indicator_requirements.execute(indicator_plan)
        strategy_reqs = self._strategy_requirements.execute(raw_spec)
        all_reqs = indicator_reqs + strategy_reqs

        winning_indicator = self._winner(indicator_reqs, base_timeframe)
        winning_strategy = self._winner(strategy_reqs, base_timeframe)

        indicator_span_ms = _span_ms(winning_indicator, base_timeframe)
        strategy_span_ms = _span_ms(winning_strategy, base_timeframe)
        required_pre_anchor_span_ms = indicator_span_ms + strategy_span_ms

        candidate_from_ms = history_anchor_open_time_ms - required_pre_anchor_span_ms
        aligned_from_ms = self._align_to_htf_buckets(
            candidate_from_ms, indicator_plan, base_timeframe
        )

        return PlannedHistoryStart(
            from_ms=aligned_from_ms,
            winning_indicator_requirement=winning_indicator,
            winning_strategy_requirement=winning_strategy,
            requirements=all_reqs,
        )

    @staticmethod
    def _winner(
        requirements: tuple[HistoryRequirement, ...], base_timeframe: str
    ) -> HistoryRequirement:
        if not requirements:
            return HistoryRequirement(timeframe="base", bars=0, reason="no requirements resolved")
        return max(requirements, key=lambda req: _span_ms(req, base_timeframe))

    @staticmethod
    def _align_to_htf_buckets(
        candidate_from_ms: int, indicator_plan: IndicatorPlan, base_timeframe: str
    ) -> int:
        """Roll candidate_from_ms back so it lands on a fixed-duration UTC
        bucket boundary for every higher timeframe present in the plan
        simultaneously (design.md Decision 8 / spec.md HTF requirement).

        Aligning to the least common multiple of all in-use HTF durations
        guarantees from_ms % d == 0 for every duration d present, since every
        such d divides the LCM by definition -- simpler and strictly
        sufficient versus per-timeframe sequential alignment, at the cost of
        (bounded) over-provisioning when multiple unrelated HTFs are in use.
        """

        htf_durations = {
            timeframe_duration_ms(_resolve_timeframe(feature.timeframe, base_timeframe))
            for feature in indicator_plan.features
            if _resolve_timeframe(feature.timeframe, base_timeframe) != base_timeframe
        }
        if not htf_durations:
            base_duration = timeframe_duration_ms(base_timeframe)
            return (candidate_from_ms // base_duration) * base_duration

        alignment_ms = timeframe_duration_ms(base_timeframe)
        for duration in htf_durations:
            alignment_ms = math.lcm(alignment_ms, duration)
        return (candidate_from_ms // alignment_ms) * alignment_ms
