"""EMA stack episode history route (OpenSpec `ema-stack-episode-query-v1`):
equality with the strategy diagnostics tables, paging by whole episodes,
the current episode and its refresh, the cache keyed by the market data
version, revalidation and the pinned version across pages."""

from __future__ import annotations

import copy
import random
import threading
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_ema_pullback_feature_range_api import minimal_spec

from strategy_engine.adapters.http.app import create_app
from strategy_engine.domain.errors import (
    InvalidRequestError,
    MarketDataVersionChangedError,
    MarketStreamNotReadyError,
    UpstreamContractError,
)
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.values import canonical_json_hash
from strategy_engine.indicators.application.catalog import IndicatorCatalog
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry, StrategyRegistry
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.application.catalog import StrategyCatalog
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.application.evaluate_range_batch import EvaluateStrategyRangeBatch
from strategy_engine.strategies.application.query_episode_history import (
    EpisodeHistoryRequest,
    QueryEpisodeHistory,
    _times,
)
from strategy_engine.strategies.application.validate_spec import ValidateStrategySpec
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.stack_episode import EpisodeParams

STEP_MS = 300_000
TOTAL_BARS = 6_000
MARKET = MarketStream("BTCUSDT.P", "5m")
PERIODS = {"fast_period": 3, "anchor_period": 8, "slow_period": 20}
WINDOW = 2
BREAK = 6
PARAMS = EpisodeParams(
    fast_period=3,
    anchor_period=8,
    slow_period=20,
    window_bars=WINDOW,
    break_bars=BREAK,
    history_bars=1,
)


class SyntheticMarket:
    """A deterministic candle path with regime changes; `visible` bars are
    committed. A candle can be repaired in place to change the history
    without changing the bounds."""

    def __init__(self, visible: int = 4_080, seed: int = 7) -> None:
        rng = random.Random(seed)
        price = 1_000.0
        drift = 0.0
        closes: list[float] = []
        self._bars: list[MarketBar] = []
        for index in range(TOTAL_BARS):
            if index % 150 == 0:
                drift = rng.choice((0.07, -0.07, 0.0, 0.05))
            opened = price
            price = max(10.0, price + drift + rng.gauss(0.0, 0.45))
            closes.append(price)
            high = max(opened, price) + abs(rng.gauss(0.0, 0.25))
            low = min(opened, price) - abs(rng.gauss(0.0, 0.25))
            self._bars.append(
                MarketBar(
                    index * STEP_MS,
                    Decimal(f"{opened:.4f}"),
                    Decimal(f"{high:.4f}"),
                    Decimal(f"{low:.4f}"),
                    Decimal(f"{price:.4f}"),
                    Decimal("10"),
                )
            )
        self.visible = visible
        self.load_range_calls = 0
        self.load_bounds_calls = 0
        self.state = "ready"

    def repair(self, index: int, delta: str = "0.5") -> None:
        bar = self._bars[index]
        self._bars[index] = MarketBar(
            bar.open_time_ms, bar.open, bar.high, bar.low, bar.close + Decimal(delta), bar.volume
        )

    def load_bounds(self, market: MarketStream) -> StreamBounds:
        self.load_bounds_calls += 1
        if self.state != "ready":
            return StreamBounds(market, self.state, None, None)
        return StreamBounds(market, "ready", 0, (self.visible - 1) * STEP_MS)

    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame:
        self.load_range_calls += 1
        first = time_range.from_ms // STEP_MS
        last = time_range.to_ms // STEP_MS
        assert last <= self.visible
        bars = tuple(self._bars[first:last])
        digest = canonical_json_hash(
            [[b.open_time_ms, str(b.open), str(b.high), str(b.low), str(b.close)] for b in bars]
        )
        if expected_market_data_hash is not None and expected_market_data_hash != digest:
            raise UpstreamContractError("coverage stale")
        return MarketFrame(market, time_range, bars, digest)

    def close(self) -> None:
        pass


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class CountingIndicators(EvaluateIndicatorRange):
    """Counts projections: one `execute_native` per computed history."""

    computed = 0

    def execute_native(self, request: Any) -> Any:
        type(self).computed += 1
        return super().execute_native(request)


def _build(
    market: SyntheticMarket, clock: Clock, *, revalidate: float = 300.0, max_entries: int = 16
) -> tuple[QueryEpisodeHistory, CountingIndicators]:
    registry = IndicatorRegistry()
    indicators = CountingIndicators(registry, market, ValidateIndicatorPlan(registry))  # type: ignore[arg-type]
    CountingIndicators.computed = 0
    service = QueryEpisodeHistory(
        market,  # type: ignore[arg-type]
        indicators,
        revalidate_seconds=revalidate,
        max_entries=max_entries,
        clock=clock,
    )
    return service, indicators


def _request(side: str = "long", **kwargs: Any) -> EpisodeHistoryRequest:
    return EpisodeHistoryRequest(market=MARKET, params=PARAMS, side=side, **kwargs)


def _all_pages(service: QueryEpisodeHistory, side: str, limit: int) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    before: int | None = None
    first_hash: str | None = None
    while True:
        page = service.execute(
            _request(
                side, before_start_ms=before, limit=limit, expected_market_data_hash=first_hash
            )
        )
        first_hash = first_hash or str(page["market_data_hash"])
        episodes.extend(page["episodes"])  # type: ignore[arg-type]
        before = page["next_before_start_ms"]  # type: ignore[assignment]
        if before is None:
            return episodes


@pytest.fixture
def world() -> tuple[SyntheticMarket, Clock, QueryEpisodeHistory]:
    market = SyntheticMarket()
    clock = Clock()
    service, _ = _build(market, clock)
    return market, clock, service


# -- equality with the strategy diagnostics (spec: Whole-history computation) ----------------


def _strategy_services(market: SyntheticMarket) -> ApplicationServices:
    registry = IndicatorRegistry()
    validate_plan = ValidateIndicatorPlan(registry)
    indicator_eval = EvaluateIndicatorRange(registry, market, validate_plan)  # type: ignore[arg-type]
    planner = BuildStrategyFeaturePlan()
    strategy_registry = StrategyRegistry(EmaPullbackRangeEvaluator(planner, indicator_eval))
    validate_strategy = ValidateStrategySpec(strategy_registry, planner)
    strategy_eval = EvaluateStrategyRange(strategy_registry, validate_strategy)
    return ApplicationServices(
        indicator_catalog=IndicatorCatalog(registry),
        validate_indicator_plan=validate_plan,
        evaluate_indicator_range=indicator_eval,
        strategy_catalog=StrategyCatalog(strategy_registry),
        validate_strategy_spec=validate_strategy,
        evaluate_strategy_range=strategy_eval,
        evaluate_strategy_range_batch=EvaluateStrategyRangeBatch(strategy_eval, market),  # type: ignore[arg-type]
        market_data_client=market,  # type: ignore[arg-type]
        build_strategy_feature_plan=planner,
    )


def _diagnostics_episode(market: SyntheticMarket, side: str) -> dict[str, Any]:
    spec = minimal_spec()
    spec["ema_stack_episode"] = {"e": {**PERIODS, "window_bars": WINDOW, "break_bars": BREAK}}
    body = {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": market.visible * STEP_MS,
        },
        "strategy": {"strategy_id": "ema_pullback", "raw_spec": spec},
        "options": {"include_features": False, "include_contexts": False},
    }
    with TestClient(create_app(services=_strategy_services(market))) as client:
        response = client.post("/v1/strategy-evaluations/range/diagnostics", json=body)
    assert response.status_code == 200, response.text
    return response.json()["ema_stack_episode"]["items"]["e"]["sides"][side]  # type: ignore[no-any-return]


@pytest.mark.parametrize("side", ["long", "short"])
def test_history_equals_the_diagnostics_tables(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory], side: str
) -> None:
    market, _, service = world
    diag = _diagnostics_episode(market, side)
    page = service.execute(_request(side, limit=500))
    finished = list(reversed(page["episodes"]))  # type: ignore[arg-type]
    current = page["current"]
    history = finished + ([current] if current else [])
    assert len(finished) >= 3, "the synthetic path must produce several finished episodes"
    assert any(e["false_breaks_count"] for e in history)
    assert sum(e["touches"] for e in history) >= 5

    def flat(name: str) -> list[Any]:
        return [entity for episode in history for entity in episode[name]]

    assert flat("zones") == _times(diag["zones"])
    assert flat("false_breaks") == _times(diag["false_breaks"])

    # The diagnostics list the final waves first and the forming ones last.
    def order(wave: dict[str, Any]) -> tuple[int, int, bool]:
        return (wave["origin"], wave["number"], wave["final"])

    assert sorted(flat("waves"), key=order) == sorted(_times(diag["waves"]), key=order)
    kept = [row for row in diag["episodes"] if not row["censored"]]
    assert [(e["start_ms"], e["stack_break_ms"]) for e in history if not e["censored"]] == [
        (row["start"]["time_ms"], row["stack_break"]["time_ms"]) for row in kept
    ]


# -- pages of whole episodes --------------------------------------------------------------


def test_pages_cover_the_history_once(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, _, service = world
    for side in ("long", "short"):
        whole = service.execute(_request(side, limit=500))
        assert whole["next_before_start_ms"] is None
        paged = _all_pages(service, side, limit=2)
        assert paged == whole["episodes"]
        starts = [e["start_ms"] for e in paged]
        assert starts == sorted(starts, reverse=True)
        assert len(set(starts)) == len(starts)
        for episode in paged:
            assert episode["stack_break_ms"] is not None
            assert [z["number"] for z in episode["zones"]] == list(
                range(1, len(episode["zones"]) + 1)
            )
    assert market.load_range_calls == 1


def test_a_page_ends_at_an_episode_boundary(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    _, _, service = world
    first = service.execute(_request(limit=2))
    assert len(first["episodes"]) == 2  # type: ignore[arg-type]
    assert first["next_before_start_ms"] == first["episodes"][-1]["start_ms"]  # type: ignore[index]
    second = service.execute(_request(limit=2, before_start_ms=first["next_before_start_ms"]))  # type: ignore[arg-type]
    assert second["episodes"][0]["start_ms"] < first["episodes"][-1]["start_ms"]  # type: ignore[index]


def test_identity_and_determinism(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    _, _, service = world
    one = service.execute(_request(limit=3))
    two = service.execute(_request(limit=3))
    assert one == two
    assert one["episode"] == {**PERIODS, "window_bars": WINDOW, "break_bars": BREAK}
    other = service.execute(
        EpisodeHistoryRequest(
            market=MARKET,
            params=EpisodeParams(3, 8, 20, 5, 5, 1),
            side="long",
            limit=3,
        )
    )
    assert other["history_id"] != one["history_id"]
    assert other["params_hash"] != one["params_hash"]
    assert other["market_data_hash"] == one["market_data_hash"]
    assert one["market"]["earliest_ms"] == 0  # type: ignore[index]
    assert one["market"]["as_of_ms"] == 4_079 * STEP_MS  # type: ignore[index]


# -- the current episode and the refresh --------------------------------------------------


def test_current_episode_and_refresh_after_new_candles(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, _, service = world
    before = _all_pages(service, "long", 500)
    first = service.execute(_request(limit=500))
    current = first["current"]
    assert current is not None and current["stack_break_ms"] is None
    assert current["phase"] in ("away", "in_zone", "in_false_break")
    market.visible += 600
    after_first = service.execute(_request(limit=500))
    assert after_first["market_data_hash"] != first["market_data_hash"]
    after = after_first["episodes"]
    assert after_first["market"]["as_of_ms"] == (market.visible - 1) * STEP_MS  # type: ignore[index]
    # Every finished episode is unchanged by newer candles; the old current
    # one may have finished, and new ones may have been added.
    by_start = {e["start_ms"]: e for e in after}  # type: ignore[union-attr]
    for episode in before:
        assert by_start[episode["start_ms"]] == episode
    assert len(after) >= len(before)  # type: ignore[arg-type]


def test_no_active_episode_gives_no_current() -> None:
    market = SyntheticMarket(visible=15)
    service, _ = _build(market, Clock())
    page = service.execute(_request(limit=5))
    assert page["episodes"] == []
    assert page["next_before_start_ms"] is None


# -- one computation per market data version ----------------------------------------------


def test_second_page_does_not_recompute(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, _, service = world
    service.execute(_request(limit=2))
    service.execute(_request("short", limit=2))
    service.execute(_request(limit=2, before_start_ms=10**12))
    assert CountingIndicators.computed == 1
    assert market.load_range_calls == 1


def test_concurrent_requests_compute_once() -> None:
    market = SyntheticMarket()
    service, _ = _build(market, Clock())
    results: list[dict[str, object]] = []
    errors: list[BaseException] = []

    def work(side: str) -> None:
        try:
            results.append(service.execute(_request(side, limit=5)))
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(("long", "short")[i % 2],)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(results) == 8
    assert CountingIndicators.computed == 1
    assert market.load_range_calls == 1


def test_a_new_candle_recomputes(world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory]) -> None:
    market, _, service = world
    service.execute(_request(limit=2))
    market.visible += 1
    service.execute(_request(limit=2))
    assert CountingIndicators.computed == 2


def test_cache_is_bounded() -> None:
    market = SyntheticMarket()
    service, _ = _build(market, Clock(), max_entries=1)
    service.execute(_request(limit=1))
    service.execute(
        EpisodeHistoryRequest(
            market=MARKET, params=EpisodeParams(3, 8, 20, 5, 5, 1), side="long", limit=1
        )
    )
    service.execute(_request(limit=1))
    assert CountingIndicators.computed == 3


def test_repaired_candle_with_unchanged_bounds_is_picked_up_after_revalidation(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, clock, service = world
    first = service.execute(_request(limit=500))
    market.repair(1_500)
    clock.now += 10.0  # inside the revalidation interval: the entry is served
    assert service.execute(_request(limit=500))["market_data_hash"] == first["market_data_hash"]
    assert CountingIndicators.computed == 1
    clock.now += 400.0
    refreshed = service.execute(_request(limit=500))
    assert refreshed["market_data_hash"] != first["market_data_hash"]
    assert CountingIndicators.computed == 2
    assert refreshed["market"] == first["market"]  # same bounds


def test_unchanged_data_after_revalidation_does_not_recompute(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, clock, service = world
    first = service.execute(_request(limit=500))
    clock.now += 400.0
    second = service.execute(_request(limit=500))
    assert second == first
    assert market.load_range_calls == 2  # reloaded to compare the hash
    assert CountingIndicators.computed == 1


# -- pinned version across pages ----------------------------------------------------------


def test_pinned_pages_of_one_version_succeed(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, _, service = world
    whole = service.execute(_request(limit=500))
    paged = _all_pages(service, "long", limit=1)  # every page pinned to the first hash
    assert paged == whole["episodes"]
    assert market.load_range_calls == 1


def test_history_changed_between_pages_fails_closed(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, clock, service = world
    first = service.execute(_request(limit=1))
    pinned = str(first["market_data_hash"])
    market.repair(1_500)
    clock.now += 400.0  # the entry is due for revalidation
    with pytest.raises(MarketDataVersionChangedError) as raised:
        service.execute(
            _request(
                limit=1,
                before_start_ms=first["next_before_start_ms"],  # type: ignore[arg-type]
                expected_market_data_hash=pinned,
            )
        )
    error = raised.value
    assert error.status_code == 409 and error.code == "market_data_version_changed"
    assert error.details["expected_market_data_hash"] == pinned
    assert error.details["actual_market_data_hash"] != pinned
    # A fresh load without a pin starts over on the new version.
    again = service.execute(_request(limit=1))
    assert again["market_data_hash"] == error.details["actual_market_data_hash"]


def test_a_wrong_pin_revalidates_once_then_fails_closed(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, _, service = world
    service.execute(_request(limit=1))
    with pytest.raises(MarketDataVersionChangedError):
        service.execute(_request(limit=1, expected_market_data_hash="not-the-hash"))
    assert market.load_range_calls == 2  # one load, one revalidation
    assert CountingIndicators.computed == 1


def test_pin_on_a_cache_miss_is_checked_against_the_fresh_load() -> None:
    market = SyntheticMarket()
    service, _ = _build(market, Clock())
    with pytest.raises(MarketDataVersionChangedError):
        service.execute(_request(limit=1, expected_market_data_hash="stale"))
    assert market.load_range_calls == 1


# -- request validation and HTTP ----------------------------------------------------------


def test_not_ready_stream_is_reported() -> None:
    market = SyntheticMarket()
    market.state = "bootstrapping"
    service, _ = _build(market, Clock())
    with pytest.raises(MarketStreamNotReadyError):
        service.execute(_request())


def test_limit_and_side_are_validated() -> None:
    with pytest.raises(InvalidRequestError):
        _request(limit=0)
    with pytest.raises(InvalidRequestError):
        _request(limit=501)
    with pytest.raises(InvalidRequestError):
        _request("both")


def _http(market: SyntheticMarket, service: QueryEpisodeHistory) -> TestClient:
    services = _strategy_services(market)
    services.query_episode_history = service
    return TestClient(create_app(services=services))


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "market": {"ticker": "BTCUSDT.P", "base_timeframe": "5m"},
        "episode": {**PERIODS, "window_bars": WINDOW, "break_bars": BREAK},
        "side": "long",
        "page": {"limit": 2},
    }
    body.update(overrides)
    return body


def test_http_route_round_trip_and_errors(
    world: tuple[SyntheticMarket, Clock, QueryEpisodeHistory],
) -> None:
    market, clock, service = world
    with _http(market, service) as client:
        ok = client.post("/v1/ema-stack-episodes/history", json=_body())
        assert ok.status_code == 200, ok.text
        payload = ok.json()
        assert len(payload["episodes"]) == 2
        assert payload["episode"]["break_bars"] == BREAK
        defaulted = client.post(
            "/v1/ema-stack-episodes/history",
            json=_body(episode={**PERIODS, "window_bars": 3}),
        ).json()
        assert defaulted["episode"]["break_bars"] == 3  # defaults to window_bars
        assert set(payload["current"]) >= {"start_ms", "touch_number", "phase", "zones"}

        pinned = client.post(
            "/v1/ema-stack-episodes/history",
            json=_body(
                page={"limit": 2, "before_start_ms": payload["next_before_start_ms"]},
                expected_market_data_hash=payload["market_data_hash"],
            ),
        )
        assert pinned.status_code == 200

        market.repair(1_500)
        clock.now += 400.0
        changed = client.post(
            "/v1/ema-stack-episodes/history",
            json=_body(expected_market_data_hash=payload["market_data_hash"]),
        )
        assert changed.status_code == 409
        assert changed.json()["error"] == "market_data_version_changed"

        for bad in (
            _body(episode={"fast_period": 3, "anchor_period": 8}),  # period missing
            _body(episode={**PERIODS, "history_bars": 100}),  # not accepted here
            _body(episode={**PERIODS, "bogus": 1}),
            _body(episode={"fast_period": 8, "anchor_period": 3, "slow_period": 20}),
            _body(side="both"),
            _body(page={"limit": 501}),
        ):
            response = client.post("/v1/ema-stack-episodes/history", json=bad)
            assert response.status_code == 422, (bad, response.text)


def test_query_and_section_share_one_parser() -> None:
    from strategy_engine.adapters.http.models import EpisodeHistoryRequestModel
    from strategy_engine.strategies.ema_pullback.stack_episode import parse_episode_section

    queried = EpisodeHistoryRequestModel.model_validate(_body()).to_domain().params
    spec = minimal_spec()
    spec["ema_stack_episode"] = {"e": {**PERIODS, "window_bars": WINDOW, "break_bars": BREAK}}
    declared = parse_episode_section(spec)["e"]
    assert (queried.fast_period, queried.anchor_period, queried.slow_period) == (
        declared.fast_period,
        declared.anchor_period,
        declared.slow_period,
    )
    assert (queried.window_bars, queried.break_bars) == (WINDOW, BREAK)
    assert (declared.window_bars, declared.break_bars) == (WINDOW, BREAK)


# -- effective parameters in the feature plan (ema-stack-episode-v1) ------------------------


def test_feature_plan_carries_effective_episode_parameters() -> None:
    spec = minimal_spec()
    spec["ema_stack_episode"] = {"trend": {}}
    plan = build_feature_plan_from_canonical_spec(spec)
    assert plan.episode_params_by_ref["trend"] == {
        "fast_period": 2,
        "anchor_period": 3,
        "slow_period": 5,
        "window_bars": 24,
        "break_bars": 24,
        "history_bars": 15000,
    }
    assert plan.to_wire()["episode_params_by_ref"] == plan.episode_params_by_ref


def test_feature_plan_without_episodes_is_unchanged() -> None:
    plan = build_feature_plan_from_canonical_spec(copy.deepcopy(minimal_spec()))
    assert plan.episode_params_by_ref == {}
    assert "episode_params_by_ref" not in plan.to_wire()
