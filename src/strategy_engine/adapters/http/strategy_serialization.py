"""Stable transport serialization for strategy range results."""

from __future__ import annotations

from strategy_engine.strategies.contracts import StrategyRangeResult


def serialize_strategy_result(result: StrategyRangeResult) -> dict[str, object]:
    feature_time = result.features.get("time_ms", []) if isinstance(result.features, dict) else []
    market_data_hash = (
        result.features.get("market_data_hash", "") if isinstance(result.features, dict) else ""
    )
    return {
        "contract_version": "strategy_evaluation.v1",
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "instance_id": result.instance_id,
        "config_hash": result.config_hash,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
            "bar_count": len(feature_time),
            "market_data_hash": market_data_hash,
        },
        "features": result.features,
        "contexts": result.contexts,
        "entries": result.entries,
        "exit_policy": result.exit_policy,
        "component_evidence": result.component_evidence,
        "validity": result.validity,
        "state_artifact": result.state_artifact,
        "warnings": list(result.warnings),
    }
