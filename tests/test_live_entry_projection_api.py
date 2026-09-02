from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.build_live_strategy_feature_plan import (
    BuildLiveStrategyFeaturePlan,
)
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.check_static_semantics import (
    CheckStrategyStaticSemantics,
)
from strategy_engine.strategies.application.evaluate_live_entry_projection import (
    EvaluateLiveEntryProjection,
)
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.load_live_feature_frame import LoadLiveFeatureFrame
from strategy_engine.strategies.application.validate_live_strategy_spec import (
    ValidateLiveStrategySpec,
)
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.contracts import LiveEntryPlan
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.live_projections.contracts import (
    EmaPullbackLiveEntryProjection,
)
from strategy_engine.strategies.live_calculation.plan_window import PlanLiveHistoryStart
from strategy_engine.strategies.live_projections.registry import LiveEntryProjectionRegistry


class FakeMarketData:
    def __init__(self, *, state: str = "ready") -> None:
        self.state = state
        self.bounds_calls = 0
        self.range_calls = 0

    def load_bounds(self, market: MarketStream) -> StreamBounds:
        self.bounds_calls += 1
        return StreamBounds(market, self.state, 0, 3_300_000)

    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame:
        del expected_market_data_hash
        self.range_calls += 1
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
            if time_range.from_ms <= index * 300_000 < time_range.to_ms
        )
        return MarketFrame(market, time_range, bars, "fixture-market-hash")

    def close(self) -> None:
        pass


def _spec(*, enabled: list[str] | None = None) -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long"] if enabled is None else enabled},
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "initial-stop",
                            "component_id": "constant_usd_stop_loss",
                            "exit_kind": "stop_loss",
                            "usd_distance": 0.25,
                        },
                        {
                            "instance_id": "initial-take",
                            "component_id": "constant_usd_take_profit",
                            "exit_kind": "take_profit",
                            "usd_distance": 0.5,
                        },
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def _payload(*, enabled: list[str] | None = None) -> dict[str, object]:
    return {
        "strategy_id": "ema_pullback",
        "raw_spec": _spec(enabled=enabled),
        "ticker": "BTCUSDT.P",
        "base_timeframe": "5m",
        "target_bar_open_time_ms": 3_300_000,
    }


class FakeLiveEntryAdapter:
    strategy_id = "ema_pullback"

    def __init__(self, plans_by_side: dict[str, LiveEntryPlan | None]) -> None:
        self._plans_by_side = plans_by_side

    def evaluate(self, request: object, bundle: object) -> EmaPullbackLiveEntryProjection:
        del request, bundle
        return EmaPullbackLiveEntryProjection(plans_by_side=self._plans_by_side)


def _entry_plan(side: str) -> LiveEntryPlan:
    stop, take = ("11.75", "12.5") if side == "long" else ("12.5", "11.75")
    return LiveEntryPlan(
        side=side,
        source_plan_bar_open_time_ms=3_300_000,
        planned_entry_price="12",
        initial_stop_price=stop,
        initial_take_price=take,
        locked_exit_profile="aligned",
    )


def _services(
    *,
    state: str = "ready",
    plans_by_side: dict[str, LiveEntryPlan | None] | None = None,
) -> tuple[ApplicationServices, FakeMarketData]:
    market_data = FakeMarketData(state=state)
    indicators = IndicatorRegistry()
    validate_plan = ValidateIndicatorPlan(indicators)
    indicator_eval = EvaluateIndicatorRange(indicators, market_data, validate_plan)
    planner = BuildStrategyFeaturePlan()
    evaluator = EmaPullbackRangeEvaluator(planner, indicator_eval)
    registry = StrategyRegistry(evaluator)
    static_semantics_checker = CheckStrategyStaticSemantics()
    validate_strategy = ValidateStrategySpec(registry, planner, static_semantics_checker)
    range_eval = EvaluateStrategyRange(registry, validate_strategy)
    live_planner = BuildLiveStrategyFeaturePlan()
    validate_live_strategy = ValidateLiveStrategySpec(
        registry, live_planner, static_semantics_checker
    )
    window_planner = PlanLiveHistoryStart(
        strategy_requirements=EmaPullbackLiveCalculationRequirements()
    )
    loader = LoadLiveFeatureFrame(
        market_data,
        live_planner,
        indicator_eval,
        validate_live_strategy,
        window_planner,
    )
    adapters = (
        LiveEntryProjectionRegistry(FakeLiveEntryAdapter(plans_by_side))
        if plans_by_side is not None
        else None
    )
    return (
        ApplicationServices(
            indicator_catalog=IndicatorCatalog(indicators),
            validate_indicator_plan=validate_plan,
            evaluate_indicator_range=indicator_eval,
            strategy_catalog=StrategyCatalog(registry),
            validate_strategy_spec=validate_strategy,
            evaluate_strategy_range=range_eval,
            evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(range_eval, market_data),
            market_data_client=market_data,  # type: ignore[arg-type]
            build_strategy_feature_plan=planner,
            load_live_feature_frame=loader,
            evaluate_live_entry_projection=EvaluateLiveEntryProjection(loader, adapters),
        ),
        market_data,
    )


def test_live_entry_http_returns_only_atomic_plan_result() -> None:
    app_services, market_data = _services()
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"desired_entry"}
    plan = body["desired_entry"]
    assert plan is not None
    assert plan["side"] == "long"
    assert plan["source_plan_bar_open_time_ms"] == 3_300_000
    assert isinstance(plan["planned_entry_price"], str)
    assert Decimal(plan["initial_stop_price"]) < Decimal(plan["planned_entry_price"])
    assert Decimal(plan["planned_entry_price"]) < Decimal(plan["initial_take_price"])
    assert market_data.bounds_calls == 1
    assert market_data.range_calls == 1


def test_live_entry_http_rejects_removed_instance_id() -> None:
    app_services, market_data = _services()
    payload = _payload()
    payload["instance_id"] = "live-1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_live_entry_http_rejects_old_nested_payload() -> None:
    app_services, market_data = _services()
    flat = _payload()
    payload = {
        "strategy": {
            "strategy_id": flat["strategy_id"],
            "raw_spec": flat["raw_spec"],
        },
        "market": {
            "ticker": flat["ticker"],
            "base_timeframe": flat["base_timeframe"],
        },
        "target_bar_open_time_ms": flat["target_bar_open_time_ms"],
    }

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_live_entry_http_returns_null_when_no_side_plan_exists() -> None:
    app_services, _ = _services(plans_by_side={"long": None, "short": None})
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=_payload())

    assert response.status_code == 200
    assert response.json() == {"desired_entry": None}


def test_live_entry_http_returns_the_single_short_plan() -> None:
    app_services, _ = _services(
        plans_by_side={"long": None, "short": _entry_plan("short")}
    )
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=_payload())

    assert response.status_code == 200
    assert response.json()["desired_entry"]["side"] == "short"


def test_live_entry_http_fails_closed_for_conflicting_side_plans() -> None:
    app_services, _ = _services(
        plans_by_side={"long": _entry_plan("long"), "short": _entry_plan("short")}
    )
    with TestClient(create_app(services=app_services), raise_server_exceptions=False) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=_payload())

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "evaluation_invariant_broken"
    assert body["details"] == {"sides": ["long", "short"]}
    assert "desired_entry" not in body


def test_live_entry_http_rejects_removed_compatibility_profile() -> None:
    app_services, market_data = _services()
    payload = _payload()
    payload["compatibility_profile"] = "bbb_v1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_live_entry_http_rejects_removed_strategy_version() -> None:
    app_services, market_data = _services()
    payload = _payload()
    payload["strategy_version"] = "v1"

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_live_entry_http_forbids_runtime_owned_history_fields() -> None:
    app_services, market_data = _services()
    request = _payload()
    request["from_ms"] = 0
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=request)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_live_entry_http_preserves_typed_not_ready_error() -> None:
    app_services, market_data = _services(state="bootstrapping")
    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=_payload())

    assert response.status_code == 409
    assert response.json()["error"] == "market_stream_not_ready"
    assert market_data.bounds_calls == 1
    assert market_data.range_calls == 0


def test_live_entry_http_rejects_duplicate_exit_instance_id() -> None:
    # Proof that the live-entry path -- ValidateLiveStrategySpec via
    # LoadLiveFeatureFrame, not ValidateStrategySpec/authoring-config
    # validation -- also enforces the restored old-BBB static semantic
    # invariants (here: exit-rule instance_id uniqueness), not just the
    # historical/authoring boundary.
    app_services, market_data = _services()
    payload = _payload()
    exits = payload["raw_spec"]["trade_management"]["exit_policy"]["always_on"]["exits"]  # type: ignore[index]
    exits[1]["instance_id"] = exits[0]["instance_id"]

    with TestClient(create_app(services=app_services)) as client:
        response = client.post("/v1/strategy-evaluations/live-entry", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert market_data.bounds_calls == 0
    assert market_data.range_calls == 0


def test_live_entry_openapi_publishes_request_and_response_contracts() -> None:
    app_services, _ = _services()
    with TestClient(create_app(services=app_services)) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/strategy-evaluations/live-entry"]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/LiveEntryProjectionRequestModel")
    assert response_ref.endswith("/LiveEntryProjectionResponseModel")
    request_schema = schema["components"]["schemas"]["LiveEntryProjectionRequestModel"]
    assert set(request_schema["properties"]) == {
        "strategy_id",
        "raw_spec",
        "ticker",
        "base_timeframe",
        "target_bar_open_time_ms",
    }
    assert "LiveMarketModel" not in schema["components"]["schemas"]
    response_schema = schema["components"]["schemas"]["LiveEntryProjectionResponseModel"]
    assert set(response_schema["properties"]) == {"desired_entry"}
    desired_entry = response_schema["properties"]["desired_entry"]
    assert desired_entry["anyOf"][0]["$ref"].endswith("/DesiredEntryResponseModel")
