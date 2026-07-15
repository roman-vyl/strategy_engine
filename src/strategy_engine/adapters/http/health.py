"""Liveness and capability-aware readiness routes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["service"])


@router.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": "strategy_engine"}


@router.get("/readiness")
def readiness() -> dict[str, object]:
    return {
        "status": "ready",
        "capabilities": {
            "catalog": "ready",
            "schema": "ready",
            "indicator_plan_structure": "ready",
            "indicator_evaluation": "ready",
            "supported_indicators": [
                "ema",
                "atr",
                "atr_distance",
                "rsi",
                "adx",
                "di_plus",
                "di_minus",
            ],
            "strategy_validation": "ready",
            "strategy_evaluation": "ready",
            "strategy_batch_evaluation": "ready",
            "managed_policy_replay": "ready",
            "runtime_bar_evaluation": "not_implemented",
        },
        "dependencies": {"market_data_service": "required_for_indicator_and_strategy_evaluation"},
    }
