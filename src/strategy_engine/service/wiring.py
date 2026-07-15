"""Composition root for foundation application services."""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy_engine.adapters.market_data_service.client import MarketDataServiceClient
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.service.settings import Settings
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.evaluate_managed_replay import EvaluateManagedReplay
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


@dataclass(slots=True)
class ApplicationServices:
    indicator_catalog: IndicatorCatalog
    validate_indicator_plan: ValidateIndicatorPlan
    evaluate_indicator_range: EvaluateIndicatorRange
    strategy_catalog: StrategyCatalog
    validate_strategy_spec: ValidateStrategySpec
    evaluate_strategy_range: EvaluateStrategyRange
    evaluate_strategy_range_batch: EvaluateStrategyRangeBatch
    market_data_client: MarketDataServiceClient
    evaluate_managed_replay: EvaluateManagedReplay | None = None
    build_strategy_feature_plan: BuildStrategyFeaturePlan = field(
        default_factory=BuildStrategyFeaturePlan
    )

    def close(self) -> None:
        self.market_data_client.close()


def build_services(settings: Settings) -> ApplicationServices:
    indicator_registry = IndicatorRegistry()
    market_data_client = MarketDataServiceClient(
        settings.mds_base_url,
        connect_timeout_seconds=settings.mds_connect_timeout_seconds,
        read_timeout_seconds=settings.mds_read_timeout_seconds,
    )
    validate_indicator_plan = ValidateIndicatorPlan(indicator_registry)
    evaluate_indicator_range = EvaluateIndicatorRange(
        indicator_registry,
        market_data_client,
        validate_indicator_plan,
    )
    build_strategy_feature_plan = BuildStrategyFeaturePlan()
    ema_pullback_evaluator = EmaPullbackRangeEvaluator(
        build_strategy_feature_plan,
        evaluate_indicator_range,
    )
    strategy_registry = StrategyRegistry(ema_pullback_evaluator)
    validate_strategy_spec = ValidateStrategySpec(
        strategy_registry,
        build_strategy_feature_plan,
    )
    evaluate_strategy_range = EvaluateStrategyRange(
        strategy_registry,
        validate_strategy_spec,
    )
    return ApplicationServices(
        indicator_catalog=IndicatorCatalog(indicator_registry),
        validate_indicator_plan=validate_indicator_plan,
        evaluate_indicator_range=evaluate_indicator_range,
        strategy_catalog=StrategyCatalog(strategy_registry),
        validate_strategy_spec=validate_strategy_spec,
        evaluate_strategy_range=evaluate_strategy_range,
        evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(evaluate_strategy_range),
        evaluate_managed_replay=EvaluateManagedReplay(
            build_strategy_feature_plan,
            evaluate_indicator_range,
            validate_strategy_spec,
        ),
        build_strategy_feature_plan=build_strategy_feature_plan,
        market_data_client=market_data_client,
    )
