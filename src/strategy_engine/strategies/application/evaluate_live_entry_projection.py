"""Generic target-bar live-entry projection application use case."""

from __future__ import annotations

from strategy_engine.strategies.application.load_live_feature_frame import (
    LiveFeatureFrameRequest,
    LoadLiveFeatureFrame,
)
from strategy_engine.strategies.contracts import (
    LiveEntryProjectionRequest,
    LiveEntryProjectionResult,
)
from strategy_engine.strategies.live_projections.defaults import (
    build_live_entry_projection_registry,
)
from strategy_engine.strategies.live_projections.registry import LiveEntryProjectionRegistry


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
            strategy_id=request.strategy.strategy_id,
            strategy_version=request.strategy.strategy_version,
            instance_id=request.strategy.instance_id,
            source_config_hash=request.strategy.config_hash,
            market=request.market,
            target_bar_open_time_ms=request.target_bar_open_time_ms,
            plans_by_side=projection.plans_by_side,
        )
