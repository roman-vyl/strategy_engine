"""Generic confirmed-open projection application use case."""

from __future__ import annotations

from strategy_engine.strategies.application.load_live_feature_frame import (
    LiveFeatureFrameRequest,
    LoadLiveFeatureFrame,
)
from strategy_engine.strategies.application.validate_open_trade_request import (
    validate_open_trade_request,
)
from strategy_engine.strategies.contracts import (
    DesiredProtection,
    OpenTradeDiagnostics,
    OpenTradeProjectionRequest,
    OpenTradeProjectionResult,
    StrategicCloseSignal,
)
from strategy_engine.strategies.live_projections.defaults import (
    build_open_trade_projection_registry,
)
from strategy_engine.strategies.live_projections.registry import OpenTradeProjectionRegistry


class EvaluateOpenTradeProjection:
    """Resolve a strategy-family adapter and compose the generic public result."""

    def __init__(
        self,
        live_frame_loader: LoadLiveFeatureFrame,
        adapters: OpenTradeProjectionRegistry | None = None,
    ) -> None:
        self._live_frame_loader = live_frame_loader
        self._adapters = adapters or build_open_trade_projection_registry()

    def execute(self, request: OpenTradeProjectionRequest) -> OpenTradeProjectionResult:
        validate_open_trade_request(request)
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
        return OpenTradeProjectionResult(
            instance_id=request.strategy.instance_id,
            strategy_id=request.strategy.strategy_id,
            strategy_version=request.strategy.strategy_version,
            market=request.market,
            target_bar_open_time_ms=request.target_bar_open_time_ms,
            desired_protection=DesiredProtection(
                projection.desired_protection.stop_price,
                projection.desired_protection.take_price,
            ),
            close_signal=StrategicCloseSignal(
                projection.close_signal.active,
                projection.close_signal.reason,
                projection.close_signal.component_id,
                projection.close_signal.layer,
            ),
            diagnostics=OpenTradeDiagnostics(
                projection.diagnostics.phase,
                projection.diagnostics.max_phase_reached,
                projection.diagnostics.bars_in_trade,
                projection.diagnostics.mfe_pct,
                projection.diagnostics.mae_pct,
                projection.diagnostics.managed_events,
            ),
        )
