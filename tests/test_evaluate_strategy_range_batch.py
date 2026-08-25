from __future__ import annotations

from decimal import Decimal

import pytest

from strategy_engine.domain.errors import InvalidRequestError, MarketDataUnavailableError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import (
    EvaluateStrategyRangeBatch,
)
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import (
    StrategyBatchVariant,
    StrategyRangeBatchRequest,
    StrategyRangeRequest,
    StrategySpecEnvelope,
)
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


class SpyMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def load_range(self, market: MarketStream, time_range: TimeRange) -> MarketFrame:
        self.calls += 1
        bars = tuple(
            MarketBar(
                index * 300_000,
                Decimal(str(index + 1)),
                Decimal(str(index + 2)),
                Decimal(str(index)),
                Decimal(str(index + 1)),
                Decimal("10"),
            )
            for index in range(12)
        )
        return MarketFrame(market, time_range, bars, "fixture-market-hash")

    def close(self) -> None:
        pass


class FailingMarketData:
    def load_range(self, market: MarketStream, time_range: TimeRange) -> MarketFrame:
        raise MarketDataUnavailableError("Market Data Service is unavailable")


def minimal_spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "components": {"blockers": []},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def _build(market_data: object) -> tuple[EvaluateStrategyRangeBatch, EvaluateStrategyRange]:
    indicator_registry = IndicatorRegistry()
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    indicator_eval = EvaluateIndicatorRange(indicator_registry, market_data, validate_plan)  # type: ignore[arg-type]
    planner = BuildStrategyFeaturePlan()
    strategy_impl = EmaPullbackRangeEvaluator(planner, indicator_eval)
    strategy_registry = StrategyRegistry(strategy_impl)
    validate_strategy = ValidateStrategySpec(strategy_registry, planner)
    strategy_eval = EvaluateStrategyRange(strategy_registry, validate_strategy)
    batch_eval = EvaluateStrategyRangeBatch(strategy_eval, market_data)  # type: ignore[arg-type]
    return batch_eval, strategy_eval


def _batch_request(count: int) -> StrategyRangeBatchRequest:
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 3_600_000)
    variants = tuple(
        StrategyBatchVariant(
            variant_id=f"variant-{index}",
            strategy=StrategySpecEnvelope(
                "ema_pullback", "v1", f"instance-{index}", minimal_spec()
            ),
        )
        for index in range(count)
    )
    return StrategyRangeBatchRequest(market=market, time_range=time_range, variants=variants)


def test_batch_with_one_variant_loads_market_data_exactly_once() -> None:
    market_data = SpyMarketData()
    batch_eval, _ = _build(market_data)
    outcomes = batch_eval.execute(_batch_request(1))
    assert market_data.calls == 1
    assert all(outcome.error is None for outcome in outcomes)


def test_batch_with_multiple_variants_loads_market_data_exactly_once() -> None:
    market_data = SpyMarketData()
    batch_eval, _ = _build(market_data)
    outcomes = batch_eval.execute(_batch_request(5))
    assert market_data.calls == 1
    assert [outcome.variant_id for outcome in outcomes] == [f"variant-{i}" for i in range(5)]
    assert all(outcome.error is None for outcome in outcomes)


def test_all_variants_consume_the_exact_same_acquired_market_frame() -> None:
    market_data = SpyMarketData()
    batch_eval, _ = _build(market_data)
    outcomes = batch_eval.execute(_batch_request(3))
    hashes = {outcome.result.features["market_data_hash"] for outcome in outcomes}  # type: ignore[union-attr]
    assert hashes == {"fixture-market-hash"}


def test_single_variant_evaluate_strategy_range_still_fetches_its_own_dataset() -> None:
    # Outside batch: EvaluateStrategyRange.execute (no market_frame) must
    # still fetch independently -- unaffected by the batch-only seam.
    market_data = SpyMarketData()
    _, strategy_eval = _build(market_data)
    strategy = StrategySpecEnvelope("ema_pullback", "v1", "solo", minimal_spec())
    request = StrategyRangeRequest(
        strategy=strategy,
        market=MarketStream("BTCUSDT.P", "5m"),
        time_range=TimeRange(0, 3_600_000),
    )
    strategy_eval.execute(request)
    assert market_data.calls == 1
    strategy_eval.execute(request)
    assert market_data.calls == 2


def test_per_variant_errors_still_envelope_after_successful_acquisition() -> None:
    market_data = SpyMarketData()
    batch_eval, _ = _build(market_data)
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 3_600_000)
    variants = (
        StrategyBatchVariant(
            "good", StrategySpecEnvelope("ema_pullback", "v1", "good", minimal_spec())
        ),
        StrategyBatchVariant(
            "bad", StrategySpecEnvelope("ema_pullback", "v1", "bad", {"anchor_stack": {}})
        ),
    )
    outcomes = batch_eval.execute(
        StrategyRangeBatchRequest(market=market, time_range=time_range, variants=variants)
    )
    assert market_data.calls == 1
    assert outcomes[0].error is None
    assert outcomes[1].error is not None
    assert outcomes[1].error["error"] == "invalid_request"


def test_shared_market_acquisition_failure_fails_the_whole_batch() -> None:
    batch_eval, _ = _build(FailingMarketData())
    with pytest.raises(MarketDataUnavailableError):
        batch_eval.execute(_batch_request(3))


def test_shared_market_acquisition_failure_precedes_per_variant_validation_errors() -> None:
    # Even when every variant's spec would independently fail validation,
    # a shared-acquisition failure still fails the whole batch rather than
    # surfacing per-variant invalid_request envelopes -- acquisition happens
    # first, before any variant is evaluated.
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 3_600_000)
    variants = (
        StrategyBatchVariant(
            "bad", StrategySpecEnvelope("ema_pullback", "v1", "bad", {"anchor_stack": {}})
        ),
    )
    batch_eval, _ = _build(FailingMarketData())
    with pytest.raises(MarketDataUnavailableError):
        batch_eval.execute(
            StrategyRangeBatchRequest(market=market, time_range=time_range, variants=variants)
        )


def test_empty_or_duplicate_variant_ids_still_rejected_before_market_acquisition() -> None:
    market_data = SpyMarketData()
    batch_eval, _ = _build(market_data)
    market = MarketStream("BTCUSDT.P", "5m")
    time_range = TimeRange(0, 3_600_000)
    with pytest.raises(InvalidRequestError):
        batch_eval.execute(
            StrategyRangeBatchRequest(market=market, time_range=time_range, variants=())
        )
    assert market_data.calls == 0
