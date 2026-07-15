"""Indicator Engine HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from strategy_engine.adapters.http.dependencies import services
from strategy_engine.adapters.http.models import IndicatorPlanModel, IndicatorRangeRequestModel
from strategy_engine.service.wiring import ApplicationServices

router = APIRouter(prefix="/v1", tags=["indicators"])


@router.get("/indicators")
def list_indicators(
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    return {"items": list(app.indicator_catalog.list())}


@router.get("/indicators/{indicator_id}/schema")
def indicator_schema(
    indicator_id: str,
    app: ApplicationServices = Depends(services),
) -> dict[str, Any]:
    return app.indicator_catalog.schema(indicator_id)


@router.post("/indicator-plans/validate")
def validate_indicator_plan(
    plan: IndicatorPlanModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    domain_plan = plan.to_domain()
    plan_hash = app.validate_indicator_plan.execute(domain_plan)
    return {"valid": True, "plan_hash": plan_hash}


@router.post("/indicator-evaluations/range")
def evaluate_indicator_range(
    request: IndicatorRangeRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    result = app.evaluate_indicator_range.execute(request.to_domain())
    return {
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
        },
        "time_ms": list(result.time_ms),
        "series": {key: list(values) for key, values in result.series.items()},
        "validity": {
            key: {
                "valid_from_ms": value.valid_from_ms,
                "warmup_bars": value.warmup_bars,
                "complete": value.complete,
                "reason": value.reason,
            }
            for key, value in result.validity.items()
        },
        "plan_hash": result.plan_hash,
        "market_data_hash": result.market_data_hash,
    }
