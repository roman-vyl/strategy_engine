from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import EmptyStrategyRegistry, IndicatorRegistry
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec


class FakeMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def load_range(self, market: MarketStream, time_range: TimeRange) -> MarketFrame:
        self.calls += 1
        bars = tuple(
            MarketBar(
                index * 300_000,
                Decimal(str(100 + index)),
                Decimal(str(102 + index)),
                Decimal(str(99 + index)),
                Decimal(str(101 + index)),
                Decimal("10"),
            )
            for index in range(5)
        )
        return MarketFrame(market, time_range, bars, "mds-fixture-hash")

    def close(self) -> None:
        pass


def services() -> tuple[ApplicationServices, FakeMarketData]:
    indicator_registry = IndicatorRegistry()
    strategy_registry = EmptyStrategyRegistry()
    market_data = FakeMarketData()
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    validate_strategy = ValidateStrategySpec(strategy_registry)
    strategy_evaluator = EvaluateStrategyRange(strategy_registry, validate_strategy)
    return (
        ApplicationServices(
            indicator_catalog=IndicatorCatalog(indicator_registry),
            validate_indicator_plan=validate_plan,
            evaluate_indicator_range=EvaluateIndicatorRange(
                indicator_registry,
                market_data,
                validate_plan,
            ),
            strategy_catalog=StrategyCatalog(strategy_registry),
            validate_strategy_spec=validate_strategy,
            evaluate_strategy_range=strategy_evaluator,
            evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(strategy_evaluator),
            market_data_client=market_data,  # type: ignore[arg-type]
        ),
        market_data,
    )


def test_mixed_ema_atr_api_uses_one_market_read() -> None:
    app_services, market_data = services()
    payload = {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 1_500_000,
        },
        "plan": {
            "plan_version": "1",
            "features": [
                {
                    "output_id": "ema_close_base_3",
                    "kind": "ema",
                    "timeframe": "base",
                    "source": "close",
                    "parameters": {"period": 3},
                    "dependencies": [],
                },
                {
                    "output_id": "atr_base_3",
                    "kind": "atr",
                    "timeframe": "base",
                    "source": "close",
                    "parameters": {"period": 3},
                    "dependencies": [],
                },
            ],
        },
    }
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/indicator-evaluations/range", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["series"]["ema_close_base_3"] == [
            "101",
            "101.5",
            "102.25",
            "103.125",
            "104.0625",
        ]
        assert body["series"]["atr_base_3"] == [None, None, "3", "3", "3"]
        assert market_data.calls == 1


def test_bad_atr_is_rejected_before_market_read() -> None:
    app_services, market_data = services()
    payload = {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 1_500_000,
        },
        "plan": {
            "plan_version": "1",
            "features": [
                {
                    "output_id": "atr_base_0",
                    "kind": "atr",
                    "timeframe": "base",
                    "source": "close",
                    "parameters": {"period": 0},
                    "dependencies": [],
                }
            ],
        },
    }
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/indicator-evaluations/range", json=payload)
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_request"
        assert market_data.calls == 0
