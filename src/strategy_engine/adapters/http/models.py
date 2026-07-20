"""FastAPI request/response models for foundation contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import (
    IndicatorPlan,
    IndicatorRangeRequest,
    PlannedFeature,
)
from strategy_engine.strategies.contracts import (
    ExecutedTradeReceipt,
    LiveEntryProjectionRequest,
    ManagedReplayRequest,
    OpenTradeProjectionRequest,
    StrategyBatchVariant,
    StrategyOutputOptions,
    StrategyRangeBatchRequest,
    StrategyRangeRequest,
    StrategySpecEnvelope,
)


class MarketRangeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: StrictStr
    base_timeframe: StrictStr
    from_ms: StrictInt
    to_ms: StrictInt

    def to_domain(self) -> tuple[MarketStream, TimeRange]:
        market = MarketStream(self.ticker, self.base_timeframe)
        time_range = TimeRange(self.from_ms, self.to_ms)
        time_range.validate_alignment(self.base_timeframe)
        return market, time_range


class PlannedFeatureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: StrictStr
    kind: StrictStr
    timeframe: StrictStr
    source: StrictStr | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[StrictStr] = Field(default_factory=list)

    def to_domain(self) -> PlannedFeature:
        return PlannedFeature(
            output_id=self.output_id,
            kind=self.kind,
            timeframe=self.timeframe,
            source=self.source,
            parameters=self.parameters,
            dependencies=tuple(self.dependencies),
        )


class IndicatorPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_version: StrictStr
    features: list[PlannedFeatureModel]

    def to_domain(self) -> IndicatorPlan:
        return IndicatorPlan(
            plan_version=self.plan_version,
            features=tuple(feature.to_domain() for feature in self.features),
        )


class IndicatorRangeRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: MarketRangeModel
    plan: IndicatorPlanModel

    def to_domain(self) -> IndicatorRangeRequest:
        market, time_range = self.market.to_domain()
        return IndicatorRangeRequest(
            market=market,
            time_range=time_range,
            plan=self.plan.to_domain(),
        )


class StrategySpecEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: StrictStr
    strategy_version: StrictStr
    instance_id: StrictStr
    raw_spec: dict[str, Any]
    compatibility_profile: StrictStr = "bbb_v1"

    def to_domain(self) -> StrategySpecEnvelope:
        return StrategySpecEnvelope(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            instance_id=self.instance_id,
            raw_spec=self.raw_spec,
            compatibility_profile=self.compatibility_profile,
        )


class StrategyOutputOptionsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_features: StrictBool = True
    include_contexts: StrictBool = True
    include_component_evidence: StrictBool = True
    include_state_artifact: StrictBool = False

    def to_domain(self) -> StrategyOutputOptions:
        return StrategyOutputOptions(
            include_features=self.include_features,
            include_contexts=self.include_contexts,
            include_component_evidence=self.include_component_evidence,
            include_state_artifact=self.include_state_artifact,
        )


class StrategyRangeRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: MarketRangeModel
    strategy: StrategySpecEnvelopeModel
    expected_market_data_hash: StrictStr | None = None
    options: StrategyOutputOptionsModel = Field(default_factory=StrategyOutputOptionsModel)

    def to_domain(self) -> StrategyRangeRequest:
        market, time_range = self.market.to_domain()
        return StrategyRangeRequest(
            strategy=self.strategy.to_domain(),
            market=market,
            time_range=time_range,
            expected_market_data_hash=self.expected_market_data_hash,
            options=self.options.to_domain(),
        )


class StrategyBatchVariantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: StrictStr
    strategy: StrategySpecEnvelopeModel

    def to_domain(self) -> StrategyBatchVariant:
        return StrategyBatchVariant(
            variant_id=self.variant_id,
            strategy=self.strategy.to_domain(),
        )


class StrategyRangeBatchRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: MarketRangeModel
    variants: list[StrategyBatchVariantModel]
    options: StrategyOutputOptionsModel = Field(default_factory=StrategyOutputOptionsModel)

    def to_domain(self) -> StrategyRangeBatchRequest:
        market, time_range = self.market.to_domain()
        return StrategyRangeBatchRequest(
            market=market,
            time_range=time_range,
            variants=tuple(variant.to_domain() for variant in self.variants),
            options=self.options.to_domain(),
        )


class LiveMarketModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: StrictStr
    base_timeframe: StrictStr

    def to_domain(self) -> MarketStream:
        return MarketStream(self.ticker, self.base_timeframe)


class LiveEntryProjectionRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategySpecEnvelopeModel
    market: LiveMarketModel
    target_bar_open_time_ms: StrictInt

    def to_domain(self) -> LiveEntryProjectionRequest:
        return LiveEntryProjectionRequest(
            strategy=self.strategy.to_domain(),
            market=self.market.to_domain(),
            target_bar_open_time_ms=self.target_bar_open_time_ms,
        )


class LiveEntryPlanResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: StrictStr
    source_plan_bar_open_time_ms: StrictInt
    planned_entry_price: StrictStr
    initial_stop_price: StrictStr
    initial_take_price: StrictStr
    locked_exit_profile: StrictStr


class LiveEntryProjectionResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: StrictStr
    strategy_id: StrictStr
    strategy_version: StrictStr
    instance_id: StrictStr
    source_config_hash: StrictStr
    market: LiveMarketModel
    target_bar_open_time_ms: StrictInt
    market_data_hash: StrictStr
    plans_by_side: dict[StrictStr, LiveEntryPlanResponseModel | None]


class ManagedReplayRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: MarketRangeModel
    strategy: StrategySpecEnvelopeModel
    trade_id: StrictStr
    side: StrictStr
    entry_time_ms: StrictInt
    entry_price: float

    def to_domain(self) -> ManagedReplayRequest:
        market, time_range = self.market.to_domain()
        if self.side not in {"long", "short"}:
            raise ValueError("side must be long or short")
        return ManagedReplayRequest(
            strategy=self.strategy.to_domain(),
            market=market,
            time_range=time_range,
            trade_id=self.trade_id,
            side=self.side,
            entry_time_ms=self.entry_time_ms,
            entry_price=float(self.entry_price),
        )


class StrategyAuthoringValidationRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instances: list[dict[str, Any]] = Field(min_length=1)


class ExecutedTradeReceiptModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: StrictStr
    instance_id: StrictStr
    strategy_id: StrictStr
    strategy_version: StrictStr
    source_config_hash: StrictStr
    ticker: StrictStr
    base_timeframe: StrictStr
    side: StrictStr
    source_plan_bar_open_time_ms: StrictInt
    entry_bar_open_time_ms: StrictInt
    planned_entry_price: StrictStr
    executed_entry_price: StrictStr
    initial_stop_price: StrictStr
    initial_take_price: StrictStr
    locked_exit_profile: StrictStr
    abi_entry_correlation: StrictStr

    def to_domain(self) -> ExecutedTradeReceipt:
        return ExecutedTradeReceipt(**self.model_dump())


class OpenTradeProjectionRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategySpecEnvelopeModel
    market: LiveMarketModel
    target_bar_open_time_ms: StrictInt
    executed_trade_receipt: ExecutedTradeReceiptModel

    def to_domain(self) -> OpenTradeProjectionRequest:
        return OpenTradeProjectionRequest(
            strategy=self.strategy.to_domain(),
            market=self.market.to_domain(),
            target_bar_open_time_ms=self.target_bar_open_time_ms,
            executed_trade_receipt=self.executed_trade_receipt.to_domain(),
        )


class DesiredProtectionResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_price: StrictStr
    take_price: StrictStr | None


class StrategicCloseSignalResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: StrictBool
    reason: StrictStr | None
    component_id: StrictStr | None
    layer: StrictStr | None


class OpenTradeDiagnosticsResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: StrictStr
    max_phase_reached: StrictStr
    bars_in_trade: StrictInt
    mfe_pct: StrictStr
    mae_pct: StrictStr
    managed_events: list[dict[str, object]]


class OpenTradeProjectionResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: StrictStr
    trade_id: StrictStr
    instance_id: StrictStr
    strategy_id: StrictStr
    strategy_version: StrictStr
    source_config_hash: StrictStr
    market: LiveMarketModel
    target_bar_open_time_ms: StrictInt
    market_data_hash: StrictStr
    desired_protection: DesiredProtectionResponseModel
    close_signal: StrategicCloseSignalResponseModel
    diagnostics: OpenTradeDiagnosticsResponseModel


class ErrorResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: StrictStr
    message: StrictStr
    details: dict[str, Any]
    request_id: StrictStr
