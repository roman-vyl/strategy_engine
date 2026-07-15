"""Concrete capability registries."""

from __future__ import annotations

from typing import Any

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.implementations import (
    RangeIndicatorEvaluator,
    validate_adx_dmi_feature,
    validate_atr_distance_feature,
    validate_atr_feature,
    validate_ema_feature,
    validate_rsi_feature,
)
from strategy_engine.indicators.ports import IndicatorEvaluator
from strategy_engine.strategies.ports import StrategyEvaluator

_EMA_SCHEMA: dict[str, Any] = {
    "indicator_id": "ema",
    "title": "Exponential Moving Average",
    "inputs": ["open", "high", "low", "close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"enum": ["open", "high", "low", "close"]},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
}


_ATR_SCHEMA: dict[str, Any] = {
    "indicator_id": "atr",
    "title": "Average True Range",
    "inputs": ["high", "low", "close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"const": "close"},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
}


_ATR_DISTANCE_SCHEMA: dict[str, Any] = {
    "indicator_id": "atr_distance",
    "title": "ATR Distance",
    "inputs": ["atr"],
    "parameters": {
        "multiplier": {"type": "number", "exclusiveMinimum": 0},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "requires_dependencies": 1,
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
    "derived_from": "atr",
}

_RSI_SCHEMA: dict[str, Any] = {
    "indicator_id": "rsi",
    "title": "Relative Strength Index",
    "inputs": ["close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"const": "close"},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
}


_ADX_SCHEMA: dict[str, Any] = {
    "indicator_id": "adx",
    "title": "Average Directional Index",
    "inputs": ["high", "low", "close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"const": "close"},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
    "calculation_group": "adx_dmi",
}

_DI_PLUS_SCHEMA = {**_ADX_SCHEMA, "indicator_id": "di_plus", "title": "Positive Directional Index"}
_DI_MINUS_SCHEMA = {
    **_ADX_SCHEMA,
    "indicator_id": "di_minus",
    "title": "Negative Directional Index",
}


class IndicatorRegistry:
    def __init__(self) -> None:
        self._evaluator = RangeIndicatorEvaluator()

    def list_definitions(self) -> tuple[dict[str, Any], ...]:
        return (
            _EMA_SCHEMA,
            _ATR_SCHEMA,
            _ATR_DISTANCE_SCHEMA,
            _RSI_SCHEMA,
            _ADX_SCHEMA,
            _DI_PLUS_SCHEMA,
            _DI_MINUS_SCHEMA,
        )

    def get_schema(self, indicator_id: str) -> dict[str, Any] | None:
        if indicator_id == "ema":
            return _EMA_SCHEMA
        if indicator_id == "atr":
            return _ATR_SCHEMA
        if indicator_id == "atr_distance":
            return _ATR_DISTANCE_SCHEMA
        if indicator_id == "rsi":
            return _RSI_SCHEMA
        if indicator_id == "adx":
            return _ADX_SCHEMA
        if indicator_id == "di_plus":
            return _DI_PLUS_SCHEMA
        if indicator_id == "di_minus":
            return _DI_MINUS_SCHEMA
        return None

    def validate_feature(self, feature: PlannedFeature) -> None:
        if feature.kind == "ema":
            validate_ema_feature(feature)
            return
        if feature.kind == "atr":
            validate_atr_feature(feature)
            return
        if feature.kind == "atr_distance":
            validate_atr_distance_feature(feature)
            return
        if feature.kind == "rsi":
            validate_rsi_feature(feature)
            return
        if feature.kind in {"adx", "di_plus", "di_minus"}:
            validate_adx_dmi_feature(feature)
            return
        raise UnsupportedCapabilityError(
            f"indicator:{feature.kind}",
            f"Indicator implementation is not ported: {feature.kind}",
        )

    def evaluator(self) -> IndicatorEvaluator:
        return self._evaluator


_EMA_PULLBACK_SCHEMA: dict[str, Any] = {
    "strategy_id": "ema_pullback",
    "title": "EMA Pullback",
    "strategy_version": "v1",
    "compatibility_profile": "bbb_v1",
    "accepted_spec_shape": "strategy_spec_to_dict",
    "supports_feature_planning": True,
    "supports_range_evaluation": True,
    "evaluation_stage": "decisions_ready",
    "supports_contexts": True,
    "supports_decisions": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
}


class StrategyRegistry:
    def __init__(self, ema_pullback_evaluator: StrategyEvaluator | None = None) -> None:
        self._ema_pullback_evaluator = ema_pullback_evaluator

    def list_definitions(self) -> tuple[dict[str, Any], ...]:
        return (_EMA_PULLBACK_SCHEMA,)

    def get_schema(self, strategy_id: str) -> dict[str, Any] | None:
        if strategy_id == "ema_pullback":
            return _EMA_PULLBACK_SCHEMA
        return None

    def evaluator(self, strategy_id: str) -> StrategyEvaluator | None:
        if strategy_id == "ema_pullback":
            return self._ema_pullback_evaluator
        return None


class EmptyStrategyRegistry:
    """Backward-compatible test registry with no strategy capabilities."""

    def list_definitions(self) -> tuple[dict[str, Any], ...]:
        return ()

    def get_schema(self, strategy_id: str) -> dict[str, Any] | None:
        return None

    def evaluator(self, strategy_id: str) -> StrategyEvaluator | None:
        return None
