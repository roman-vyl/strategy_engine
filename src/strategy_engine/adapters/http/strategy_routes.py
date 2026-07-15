"""Strategy Engine HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from strategy_engine.adapters.http.dependencies import services
from strategy_engine.adapters.http.models import (
    ManagedReplayRequestModel,
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


@router.post("/strategy-evaluations/managed-replay")
def evaluate_managed_replay(
    request: ManagedReplayRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    if app.evaluate_managed_replay is None:
        from strategy_engine.domain.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError("strategy:managed_replay")
    return app.evaluate_managed_replay.execute(request.to_domain()).to_wire()
