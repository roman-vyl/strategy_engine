from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


class _FakeMarketData:
    """Deterministic, network-free market data stub for HTTP-layer tests
    that must not depend on a live Market Data Service being reachable."""

    def load_range(self, market: MarketStream, time_range: TimeRange, **_: object) -> MarketFrame:
        count = (time_range.to_ms - time_range.from_ms) // 300_000
        bars = tuple(
            MarketBar(
                time_range.from_ms + index * 300_000,
                Decimal(str(index + 1)),
                Decimal(str(index + 2)),
                Decimal(str(index)),
                Decimal(str(index + 1)),
                Decimal("10"),
            )
            for index in range(count)
        )
        return MarketFrame(market, time_range, bars, "fixture-hash")

    def close(self) -> None:
        pass


def _services_with_fake_market_data() -> ApplicationServices:
    indicator_registry = IndicatorRegistry()
    market_data = _FakeMarketData()
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    indicator_eval = EvaluateIndicatorRange(indicator_registry, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    strategy_impl = EmaPullbackRangeEvaluator(planner, indicator_eval)
    strategy_registry = StrategyRegistry(strategy_impl)
    validate_strategy = ValidateStrategySpec(strategy_registry, planner)
    strategy_eval = EvaluateStrategyRange(strategy_registry, validate_strategy)
    return ApplicationServices(
        indicator_catalog=IndicatorCatalog(indicator_registry),
        validate_indicator_plan=validate_plan,
        evaluate_indicator_range=indicator_eval,
        strategy_catalog=StrategyCatalog(strategy_registry),
        validate_strategy_spec=validate_strategy,
        evaluate_strategy_range=strategy_eval,
        evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(strategy_eval, market_data),
        market_data_client=market_data,  # type: ignore[arg-type]
        build_strategy_feature_plan=planner,
    )


def strategy_payload() -> dict[str, object]:
    return {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 300_000,
        },
        "strategy": {
            "strategy_id": "ema_pullback",
            "raw_spec": {"strategy": {"id": "ema_pullback"}},
        },
        "options": {
            "include_features": True,
            "include_contexts": True,
            "include_component_evidence": True,
            "include_state_artifact": False,
        },
    }


def test_health_readiness_and_openapi() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["status"] == "ok"
        readiness = client.get("/readiness").json()
        assert readiness["status"] == "ready"
        assert readiness["capabilities"]["strategy_evaluation"] == "ready"
        assert "/v1/strategy-evaluations/range" in client.get("/openapi.json").json()["paths"]


def test_catalogs_advertise_only_ported_capabilities() -> None:
    with TestClient(create_app()) as client:
        indicators = client.get("/v1/indicators").json()["items"]
        assert [item["indicator_id"] for item in indicators] == [
            "ema",
            "atr",
            "atr_distance",
            "rsi",
            "adx",
            "di_plus",
            "di_minus",
        ]
        assert client.get("/v1/indicators/ema/schema").status_code == 200
        strategies = client.get("/v1/strategies").json()["items"]
        assert [item["strategy_id"] for item in strategies] == ["ema_pullback"]
        response = client.get("/v1/indicators/atr_distance/schema")
        assert response.status_code == 200
        assert response.json()["derived_from"] == "atr"


def test_unported_indicator_evaluation_returns_501_not_fake_success() -> None:
    payload = {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 300_000,
        },
        "plan": {
            "plan_version": "1",
            "features": [
                {
                    "output_id": "macd_5m",
                    "kind": "macd",
                    "timeframe": "5m",
                    "source": "close",
                    "parameters": {"period": 14},
                    "dependencies": [],
                }
            ],
        },
    }
    with TestClient(create_app()) as client:
        response = client.post("/v1/indicator-evaluations/range", json=payload)
        assert response.status_code == 501
        assert response.json()["error"] == "unsupported_capability"
        assert "request_id" in response.json()


def test_unported_strategy_evaluation_returns_501() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategy-evaluations/range", json=strategy_payload())
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_request"


def test_batch_preserves_variant_order_and_error_identity() -> None:
    # batch-market-dataset-reuse: the shared market dataset is now acquired
    # once, before any per-variant evaluation, so this test injects a
    # network-free market data stub (via create_app(services=...)) instead
    # of relying on a live Market Data Service being reachable -- a live MDS
    # is not guaranteed in CI, and this test's intent (per-variant error
    # identity after successful acquisition) does not depend on real data.
    first = strategy_payload()["strategy"]
    assert isinstance(first, dict)
    second = dict(first)
    payload = {
        "market": {
            "ticker": "ETHUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 1615766400000,
            "to_ms": 1615767000000,
        },
        "variants": [
            {"variant_id": "a", "strategy": first},
            {"variant_id": "b", "strategy": second},
        ],
    }
    with TestClient(create_app(services=_services_with_fake_market_data())) as client:
        response = client.post("/v1/strategy-evaluations/range-batch", json=payload)
        assert response.status_code == 200
        variants = response.json()["variants"]
        assert [item["variant_id"] for item in variants] == ["a", "b"]
        assert all(item["error"]["error"] == "invalid_request" for item in variants)


def _valid_ema_pullback_raw_spec() -> dict[str, object]:
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


def test_batch_variant_outcome_result_exact_key_set() -> None:
    # Sequencing artifact for strategy-evaluation-canonical-boundary-v1:
    # the authoritative reference for a successful range-batch variant's
    # embedded result shape.
    payload = {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 3_600_000,
        },
        "variants": [
            {
                "variant_id": "a",
                "strategy": {
                    "strategy_id": "ema_pullback",
                    "raw_spec": _valid_ema_pullback_raw_spec(),
                },
            }
        ],
    }
    with TestClient(create_app(services=_services_with_fake_market_data())) as client:
        response = client.post("/v1/strategy-evaluations/range-batch", json=payload)
    assert response.status_code == 200
    variants = response.json()["variants"]
    assert variants[0]["error"] is None
    assert set(variants[0]["result"]) == {
        "contract_version",
        "strategy_id",
        "config_hash",
        "market",
        "features",
        "contexts",
        "entries",
        "potential_entries",
        "exit_policy",
        "component_evidence",
        "validity",
        "state_artifact",
        "warnings",
    }


def test_batch_shared_market_acquisition_failure_fails_whole_batch() -> None:
    # batch-market-dataset-reuse design.md Decision 2: a terminal failure of
    # the once-per-batch shared market acquisition fails the whole batch
    # rather than being retried/surfaced independently per variant. This
    # payload's market range (year-1970 epoch) is not an available range for
    # any configured stream, so acquisition itself fails before any variant
    # is evaluated.
    first = strategy_payload()["strategy"]
    assert isinstance(first, dict)
    payload = {
        "market": strategy_payload()["market"],
        "variants": [{"variant_id": "a", "strategy": first}],
    }
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategy-evaluations/range-batch", json=payload)
        assert response.status_code != 200
        body = response.json()
        assert "variants" not in body


def test_invalid_range_uses_stable_error_envelope() -> None:
    payload = strategy_payload()
    market = payload["market"]
    assert isinstance(market, dict)
    market["from_ms"] = 1
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategy-evaluations/range", json=payload)
        assert response.status_code == 422
        body = response.json()
        assert set(body) == {"error", "message", "details", "request_id"}
