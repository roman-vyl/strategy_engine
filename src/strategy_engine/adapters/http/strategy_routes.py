"""Strategy Engine HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from strategy_engine.adapters.http.dependencies import services
from strategy_engine.adapters.http.models import (
    DesiredProtectionResponseModel,
    ErrorResponseModel,
    LiveEntryProjectionRequestModel,
    LiveEntryProjectionResponseModel,
    LiveMarketModel,
    ManagedReplayRequestModel,
    OpenTradeDiagnosticsResponseModel,
    OpenTradeProjectionRequestModel,
    OpenTradeProjectionResponseModel,
    StrategicCloseSignalResponseModel,
    StrategyAuthoringValidationRequestModel,
    StrategyRangeBatchRequestModel,
    StrategyRangeRequestModel,
    StrategySpecEnvelopeModel,
)
from strategy_engine.adapters.http.strategy_serialization import serialize_strategy_result
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.ema_pullback.authoring import authoring_instance_to_envelope
from strategy_engine.strategies.ema_pullback.composer_catalog import get_component_catalog

router = APIRouter(prefix="/v1", tags=["strategies"])


@router.get("/strategies")
def list_strategies(
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    return {"items": list(app.strategy_catalog.list())}


@router.get("/strategies/{strategy_id}/schema")
def strategy_schema(
    strategy_id: str,
    app: ApplicationServices = Depends(services),
) -> dict[str, Any]:
    return app.strategy_catalog.schema(strategy_id)


@router.get("/strategies/{strategy_id}/composer-catalog")
def strategy_composer_catalog(strategy_id: str) -> dict[str, Any]:
    if strategy_id != "ema_pullback":
        from strategy_engine.domain.errors import UnknownResourceError

        raise UnknownResourceError("unknown strategy", strategy_id=strategy_id)
    return get_component_catalog(family=strategy_id).model_dump(mode="json")


@router.post("/strategies/{strategy_id}/validate")
def validate_strategy(
    strategy_id: str,
    strategy: StrategySpecEnvelopeModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    if strategy_id != strategy.strategy_id:
        from strategy_engine.domain.errors import InvalidRequestError

        raise InvalidRequestError(
            "path strategy_id does not match request strategy_id",
            path_strategy_id=strategy_id,
            request_strategy_id=strategy.strategy_id,
        )
    config_hash = app.validate_strategy_spec.execute(strategy.to_domain())
    return {"valid": True, "config_hash": config_hash}


@router.post("/strategies/{strategy_id}/authoring-config/validate")
def validate_authoring_config(
    strategy_id: str,
    request: StrategyAuthoringValidationRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    if strategy_id != "ema_pullback":
        from strategy_engine.domain.errors import UnknownResourceError

        raise UnknownResourceError("unknown strategy", strategy_id=strategy_id)
    validated = []
    for index, instance in enumerate(request.instances):
        try:
            envelope = authoring_instance_to_envelope(instance)
            config_hash = app.validate_strategy_spec.execute(envelope)
            validated.append(
                {"index": index, "instance_id": envelope.instance_id, "config_hash": config_hash}
            )
        except Exception as exc:
            return {
                "valid": False,
                "errors": [{"path": f"instances[{index}]", "message": str(exc)}],
            }
    return {"valid": True, "errors": [], "instances": validated}


@router.post("/strategies/{strategy_id}/feature-plan")
def build_strategy_feature_plan(
    strategy_id: str,
    strategy: StrategySpecEnvelopeModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    if strategy_id != strategy.strategy_id:
        from strategy_engine.domain.errors import InvalidRequestError

        raise InvalidRequestError(
            "path strategy_id does not match request strategy_id",
            path_strategy_id=strategy_id,
            request_strategy_id=strategy.strategy_id,
        )
    domain_strategy = strategy.to_domain()
    app.validate_strategy_spec.execute(domain_strategy)
    return app.build_strategy_feature_plan.execute(domain_strategy).to_wire()


def _serialize_live_entry_projection(result: object) -> dict[str, object]:
    from strategy_engine.strategies.contracts import LiveEntryProjectionResult

    if not isinstance(result, LiveEntryProjectionResult):
        raise TypeError("expected LiveEntryProjectionResult")
    return {
        "strategy_id": result.strategy_id,
        "instance_id": result.instance_id,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
        },
        "target_bar_open_time_ms": result.target_bar_open_time_ms,
        "plans_by_side": {
            side: (
                {
                    "side": plan.side,
                    "source_plan_bar_open_time_ms": plan.source_plan_bar_open_time_ms,
                    "planned_entry_price": plan.planned_entry_price,
                    "initial_stop_price": plan.initial_stop_price,
                    "initial_take_price": plan.initial_take_price,
                    "locked_exit_profile": plan.locked_exit_profile,
                }
                if plan is not None
                else None
            )
            for side, plan in result.plans_by_side.items()
        },
    }


def _serialize_open_trade_projection(result: object) -> OpenTradeProjectionResponseModel:
    from strategy_engine.strategies.contracts import OpenTradeProjectionResult

    if not isinstance(result, OpenTradeProjectionResult):
        raise TypeError("expected OpenTradeProjectionResult")
    return OpenTradeProjectionResponseModel(
        instance_id=result.instance_id,
        strategy_id=result.strategy_id,
        market=LiveMarketModel(
            ticker=result.market.ticker,
            base_timeframe=result.market.base_timeframe,
        ),
        target_bar_open_time_ms=result.target_bar_open_time_ms,
        desired_protection=DesiredProtectionResponseModel(
            stop_price=result.desired_protection.stop_price,
            take_price=result.desired_protection.take_price,
        ),
        close_signal=StrategicCloseSignalResponseModel(
            active=result.close_signal.active,
            reason=result.close_signal.reason,
            component_id=result.close_signal.component_id,
            layer=result.close_signal.layer,
        ),
        diagnostics=OpenTradeDiagnosticsResponseModel(
            phase=result.diagnostics.phase,
            max_phase_reached=result.diagnostics.max_phase_reached,
            bars_in_trade=result.diagnostics.bars_in_trade,
            mfe_pct=result.diagnostics.mfe_pct,
            mae_pct=result.diagnostics.mae_pct,
            managed_events=list(result.diagnostics.managed_events),
        ),
    )


@router.post("/strategy-evaluations/range")
def evaluate_strategy_range(
    request: StrategyRangeRequestModel,
    app: ApplicationServices = Depends(services),
) -> Any:
    return serialize_strategy_result(app.evaluate_strategy_range.execute(request.to_domain()))


@router.post("/strategy-evaluations/range-batch")
def evaluate_strategy_range_batch(
    request: StrategyRangeBatchRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    outcomes = app.evaluate_strategy_range_batch.execute(request.to_domain())
    return {
        "variants": [
            {
                "variant_id": outcome.variant_id,
                "result": (
                    serialize_strategy_result(outcome.result)
                    if outcome.result is not None
                    else None
                ),
                "error": outcome.error,
            }
            for outcome in outcomes
        ]
    }


@router.post(
    "/strategy-evaluations/live-entry",
    response_model=LiveEntryProjectionResponseModel,
    responses={
        404: {"model": ErrorResponseModel},
        409: {"model": ErrorResponseModel},
        422: {"model": ErrorResponseModel},
        501: {"model": ErrorResponseModel},
        502: {"model": ErrorResponseModel},
        503: {"model": ErrorResponseModel},
        500: {"model": ErrorResponseModel},
    },
)
def evaluate_live_entry_projection(
    request: LiveEntryProjectionRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    if app.evaluate_live_entry_projection is None:
        from strategy_engine.domain.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError("strategy:live_entry_projection")
    result = app.evaluate_live_entry_projection.execute(request.to_domain())
    return _serialize_live_entry_projection(result)


@router.post(
    "/strategy-evaluations/open-trade",
    response_model=OpenTradeProjectionResponseModel,
    responses={
        404: {"model": ErrorResponseModel},
        409: {"model": ErrorResponseModel},
        422: {"model": ErrorResponseModel},
        501: {"model": ErrorResponseModel},
        502: {"model": ErrorResponseModel},
        503: {"model": ErrorResponseModel},
        500: {"model": ErrorResponseModel},
    },
)
def evaluate_open_trade_projection(
    request: OpenTradeProjectionRequestModel,
    app: ApplicationServices = Depends(services),
) -> OpenTradeProjectionResponseModel:
    if app.evaluate_open_trade_projection is None:
        from strategy_engine.domain.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError("strategy:open_trade_projection")
    result = app.evaluate_open_trade_projection.execute(request.to_domain())
    return _serialize_open_trade_projection(result)


@router.post("/strategy-evaluations/managed-replay")
def evaluate_managed_replay(
    request: ManagedReplayRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    if app.evaluate_managed_replay is None:
        from strategy_engine.domain.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError("strategy:managed_replay")
    return app.evaluate_managed_replay.execute(request.to_domain()).to_wire()
