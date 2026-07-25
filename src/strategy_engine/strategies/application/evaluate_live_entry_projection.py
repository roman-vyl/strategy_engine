"""Generic target-bar live-entry projection application use case."""

from __future__ import annotations

from strategy_engine.domain.errors import EvaluationInvariantError
from strategy_engine.strategies.application.load_live_feature_frame import (
    LiveFeatureFrameRequest,
    LoadLiveFeatureFrame,
)
from strategy_engine.strategies.contracts import (
    DesiredEntry,
    LiveEntryPlan,
    LiveEntryProjectionRequest,
    LiveEntryProjectionResult,
)
from strategy_engine.strategies.live_projections.defaults import (
    build_live_entry_projection_registry,
)
from strategy_engine.strategies.live_projections.registry import LiveEntryProjectionRegistry


def _normalize_desired_entry(
    plans_by_side: dict[str, LiveEntryPlan | None],
) -> DesiredEntry | None:
    available = tuple(plan for plan in plans_by_side.values() if plan is not None)
    if len(available) > 1:
        raise EvaluationInvariantError(
            "live-entry adapter returned conflicting side plans",
            sides=tuple(plan.side for plan in available),
        )
    if not available:
        return None
    plan = available[0]
    return DesiredEntry(
        side=plan.side,
        source_plan_bar_open_time_ms=plan.source_plan_bar_open_time_ms,
        planned_entry_price=plan.planned_entry_price,
        initial_stop_price=plan.initial_stop_price,
        initial_take_price=plan.initial_take_price,
        locked_exit_profile=plan.locked_exit_profile,
    )


class EvaluateLiveEntryProjection:
    """Resolve a strategy-family adapter and compose the generic public result."""

    def __init__(
        self,
        live_frame_loader: LoadLiveFeatureFrame,
        adapters: LiveEntryProjectionRegistry | None = None,
    ) -> None:
        self._live_frame_loader = live_frame_loader
        self._adapters = adapters or build_live_entry_projection_registry()

    def execute(self, request: LiveEntryProjectionRequest) -> LiveEntryProjectionResult:
        bundle = self._live_frame_loader.execute(
            LiveFeatureFrameRequest(
                strategy=request.strategy,
                market=request.market,
                target_bar_open_time_ms=request.target_bar_open_time_ms,
            )
        )
        projection = self._adapters.resolve(request.strategy.strategy_id).evaluate(
            request, bundle
        )
        return LiveEntryProjectionResult(
            desired_entry=_normalize_desired_entry(projection.plans_by_side),
        )
