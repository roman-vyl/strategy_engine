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
        return MarketFrame(market, time_range, bars, "fixture")

    def close(self) -> None:
        pass


def services() -> tuple[ApplicationServices, FakeMarketData]:
    indicators = IndicatorRegistry()
    strategies = EmptyStrategyRegistry()
    market_data = FakeMarketData()
    validate_plan = ValidateIndicatorPlan(indicators)
    validate_strategy = ValidateStrategySpec(strategies)
    strategy_eval = EvaluateStrategyRange(strategies, validate_strategy)
    return (
        ApplicationServices(
            indicator_catalog=IndicatorCatalog(indicators),
            validate_indicator_plan=validate_plan,
            evaluate_indicator_range=EvaluateIndicatorRange(
                indicators,
                market_data,
                validate_plan,
            ),
            strategy_catalog=StrategyCatalog(strategies),
            validate_strategy_spec=validate_strategy,
            evaluate_strategy_range=strategy_eval,
            evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(strategy_eval),
            market_data_client=market_data,  # type: ignore[arg-type]
        ),
        market_data,
    )


def test_atr_distance_api_uses_one_market_read() -> None:
    app, market_data = services()
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
                    "output_id": "atr_base_3",
                    "kind": "atr",
                    "timeframe": "base",
                    "source": "close",
                    "parameters": {"period": 3},
                    "dependencies": [],
                },
                {
                    "output_id": "atr_base_3_x2",
                    "kind": "atr_distance",
                    "timeframe": "base",
                    "source": None,
                    "parameters": {"multiplier": 2},
                    "dependencies": ["atr_base_3"],
                },
            ],
        },
    }
    with TestClient(create_app(services=app)) as client:
        response = client.post("/v1/indicator-evaluations/range", json=payload)
        assert response.status_code == 200
        assert response.json()["series"]["atr_base_3_x2"] == [
            None,
            None,
            "6",
            "6",
            "6",
        ]
        assert market_data.calls == 1
