"""Structural indicator-plan validation."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError, UnsupportedCapabilityError
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.indicators.ports import IndicatorRegistryPort


class ValidateIndicatorPlan:
    def __init__(self, registry: IndicatorRegistryPort) -> None:
        self._registry = registry

    def execute(self, plan: IndicatorPlan) -> str:
        output_ids = [feature.output_id for feature in plan.features]
        if not plan.plan_version:
            raise InvalidRequestError("plan_version is required")
        if not output_ids:
            raise InvalidRequestError("indicator plan must contain at least one feature")
        if len(output_ids) != len(set(output_ids)):
            raise InvalidRequestError("feature output_id values must be unique")
        known = {item["indicator_id"] for item in self._registry.list_definitions()}
        for feature in plan.features:
            if not feature.output_id or not feature.kind:
                raise InvalidRequestError("feature output_id and kind are required")
            if feature.timeframe != "base":
                timeframe_duration_ms(feature.timeframe)
            missing = [
                dependency for dependency in feature.dependencies if dependency not in output_ids
            ]
            if missing:
                raise InvalidRequestError(
                    "feature dependency is not present in the plan",
                    output_id=feature.output_id,
                    missing_dependencies=missing,
                )
            if feature.kind == "atr_distance":
                dependency_id = feature.dependencies[0] if feature.dependencies else None
                dependency_index = (
                    output_ids.index(dependency_id) if dependency_id in output_ids else -1
                )
                current_index = output_ids.index(feature.output_id)
                if dependency_index >= current_index:
                    raise InvalidRequestError(
                        "atr_distance dependency must appear earlier in the plan",
                        output_id=feature.output_id,
                        dependency=dependency_id,
                    )
                dependency_feature = plan.features[dependency_index]
                if dependency_feature.kind != "atr":
                    raise InvalidRequestError(
                        "atr_distance dependency must reference an ATR feature",
                        output_id=feature.output_id,
                        dependency=dependency_id,
                    )
                if dependency_feature.timeframe != feature.timeframe:
                    raise InvalidRequestError(
                        "atr_distance timeframe must match its ATR dependency",
                        output_id=feature.output_id,
                        dependency=dependency_id,
                    )
            if feature.kind not in known:
                raise UnsupportedCapabilityError(
                    f"indicator:{feature.kind}",
                    f"Indicator implementation is not ported: {feature.kind}",
                )
            self._registry.validate_feature(feature)
        return plan.plan_hash
