"""`change_since_entry` (OpenSpec `entry-anchored-change-v1`): static
contract, the formula, single-trade evaluation against a naive per-bar
reference on the parity market fixture (including higher-timeframe entries
between two closes of that timeframe), projection shape and serialization,
feature planning and live history."""

from __future__ import annotations

import copy
import math
from typing import Any

import pytest
from parity.composite_phase_corpus import (
    DI1H,
    MFE_PCT,
    RISE_ADX1H,
    _composite,
    _cond,
    _feature,
    _pred,
    _spec,
    entry_change_at_least,
    entry_change_case,
    owner_case,
)

from strategy_engine.adapters.http.strategy_serialization import _serialize_path
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.strategies.ema_pullback.entry_change import (
    ChangeSinceEntry,
    parse_change_since_entry,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.historical_managed_projection import (
    build_historical_managed_projection,
)
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.managed import (
    evaluate_managed_replay,
    evaluate_start_after_entry_managed_projection,
)
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]

_HOUR_MS = timeframe_duration_ms("1h")


def _rise(timeframe: str, op: str, value: float) -> dict[str, Any]:
    return {
        "component_id": "change_since_entry",
        "params": {"operand": _feature("adx", timeframe), "op": op, "value": value},
    }


def _single(change: dict[str, Any]) -> dict[str, Any]:
    return _composite([_cond("rise", change)], [{"path_id": "rise", "require": ["rise"]}])


# -- 1.1 / 1.2 static contract -----------------------------------------------------


@pytest.mark.parametrize(
    "condition",
    [entry_change_case(), entry_change_at_least()],
    ids=["require", "at-least"],
)
def test_entry_change_children_are_accepted(condition: dict[str, Any]) -> None:
    check_ema_pullback_static_semantics(_spec(condition))


@pytest.mark.parametrize("op", [">=", ">", "<=", "<"])
def test_all_operators_and_negative_values_are_accepted(op: str) -> None:
    check_ema_pullback_static_semantics(_spec(_single(_rise("1h", op, -3.5))))


def _with_params(**changes: Any) -> dict[str, Any]:
    change = copy.deepcopy(RISE_ADX1H)
    for key, value in changes.items():
        if value is _DELETE:
            del change["params"][key]
        else:
            change["params"][key] = value
    return _single(change)


_DELETE = object()


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param(_with_params(op="=="), id="equality"),
        pytest.param(_with_params(op="!="), id="inequality"),
        pytest.param(_with_params(value=math.inf), id="non-finite-value"),
        pytest.param(_with_params(value=True), id="bool-value"),
        pytest.param(_with_params(value=_DELETE), id="missing-value"),
        pytest.param(_with_params(op=_DELETE), id="missing-op"),
        pytest.param(_with_params(lookback=3), id="lookback"),
        pytest.param(_with_params(short={"value": 1.0}), id="short-override"),
        pytest.param(_with_params(extra=1), id="unknown-field"),
        pytest.param(_with_params(operand={"price": "close"}), id="price-operand"),
        pytest.param(_with_params(operand={"const": 1.0}), id="const-operand"),
        pytest.param(
            _with_params(operand={"feature": {"kind": "nope", "params": {}}}), id="unknown-kind"
        ),
    ],
)
def test_invalid_entry_change_is_rejected(condition: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec(condition))


def test_entry_change_is_not_a_phase_rule_condition() -> None:
    with pytest.raises(InvalidRequestError, match="change_since_entry is not a phase_rule"):
        check_ema_pullback_static_semantics(_spec(copy.deepcopy(RISE_ADX1H)))


def test_entry_change_is_not_a_setup_child() -> None:
    spec = _spec(owner_case())
    spec["setups"] = [
        {
            "component_id": "composite_setup",
            "instance_id": "c",
            "params": {
                "children": [{"child_id": "rise", "predicate": copy.deepcopy(RISE_ADX1H)}],
                "paths": [{"path_id": "p", "require": ["rise"]}],
            },
        }
    ]
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(spec)


# -- the formula (design D4) ------------------------------------------------------


@pytest.mark.parametrize(
    ("op", "current", "anchor", "expected"),
    [
        (">=", 26.0, 21.0, True),
        (">=", 25.9, 21.0, False),
        (">", 26.0, 21.0, False),
        (">", 26.1, 21.0, True),
        ("<=", 16.0, 21.0, True),
        ("<", 16.0, 21.0, False),
        (">=", None, 21.0, False),
        (">=", 26.0, None, False),
        (">=", math.nan, 21.0, False),
        (">=", 26.0, math.inf, False),
    ],
)
def test_change_formula(op: str, current: Any, anchor: Any, expected: bool) -> None:
    change = parse_change_since_entry(
        {"operand": _feature("adx", "1h"), "op": op, "value": 5.0 if op in (">=", ">") else -5.0},
        "x",
    )
    assert isinstance(change, ChangeSinceEntry)
    assert change.met(current, anchor) is expected


# -- 2.x single-trade evaluation against a naive reference -------------------------


@pytest.fixture(scope="module")
def fixture_frame() -> tuple[Any, Any, Any, Any]:
    """(frame, plan, services market, time range) of the parity market
    fixture for a spec planning 1h and 5m ADX/DI."""

    from parity.harness import market_fixture_meta
    from parity.managed_invariants import _slice_services

    from strategy_engine.domain.market import MarketStream
    from strategy_engine.domain.ranges import TimeRange
    from strategy_engine.indicators.contracts import IndicatorRangeRequest
    from strategy_engine.strategies.contracts import LiveStrategySpec

    meta = market_fixture_meta()
    market = MarketStream(meta["ticker"], meta["timeframe"])
    time_range = TimeRange(meta["from_ms"], meta["to_ms"])
    raw = _spec(entry_change_case(), entry_change_at_least(), to_phases=("proven", "runner"))
    with _slice_services() as services:
        plan = services.build_strategy_feature_plan.execute(
            LiveStrategySpec("ema_pullback", raw)  # type: ignore[arg-type]
        )
        frame = services.evaluate_indicator_range.execute(
            IndicatorRangeRequest(market, time_range, plan.indicator_plan)
        )
    return frame, plan, market, time_range


def _column(frame: Any, timeframe: str) -> list[float]:
    label = next(
        feature.output_id
        for feature in parse_predicate(
            {
                "kind": "compare",
                "left": _feature("adx", timeframe),
                "op": ">",
                "right": {"const": 0},
            },
            "x",
        ).features()
    )
    return [math.nan if v is None else float(v) for v in frame.series[label]]


def _replay(raw: Spec, frame: Any, plan: Any, side: str, entry: int) -> Any:
    return evaluate_managed_replay(
        raw,
        frame,
        plan,
        trade_id="T",
        side=side,  # type: ignore[arg-type]
        entry_time_ms=frame.time_ms[entry],
        entry_price=float(frame.market_bars[entry].close),
    )


def _transitions(result: Any) -> list[tuple[int, dict[str, Any]]]:
    return [(e.bar_index, e.metadata) for e in result.events if e.event_type == "phase_changed"]


def _naive_first(series: list[float], entry: int, op: str, value: float) -> int | None:
    ops = {">=": float.__ge__, ">": float.__gt__, "<=": float.__le__, "<": float.__lt__}
    anchor = series[entry]
    if not math.isfinite(anchor):
        return None
    for index in range(entry, len(series)):
        current = series[index]
        if math.isfinite(current) and ops[op](current - anchor, value):
            return index
    return None


@pytest.mark.parametrize("timeframe", ["5m", "1h"])
@pytest.mark.parametrize(("op", "value"), [(">=", 3.0), (">", 0.0), ("<=", -2.0), ("<", -4.0)])
def test_replay_matches_naive_reference(
    fixture_frame: Any, timeframe: str, op: str, value: float
) -> None:
    frame, plan, _, _ = fixture_frame
    raw = _spec(_single(_rise(timeframe, op, value)))
    series = _column(frame, timeframe)
    fired = 0
    for side in ("long", "short"):
        for entry in range(150, len(frame.time_ms) - 1, 613):
            expected = _naive_first(series, entry, op, value)
            got = _transitions(_replay(raw, frame, plan, side, entry))
            if expected is None:
                assert got == [], (side, entry)
                continue
            assert got == [(expected, {"path_id": "rise", "children": {"rise": True}})], (
                side,
                entry,
            )
            fired += 1
    assert fired >= 10, fired


def test_entry_bar_itself_is_zero_change(fixture_frame: Any) -> None:
    frame, plan, _, _ = fixture_frame
    raw = _spec(_single(_rise("1h", ">=", 0.0)))
    series = _column(frame, "1h")
    entry = next(i for i, v in enumerate(series) if math.isfinite(v)) + 7
    assert _transitions(_replay(raw, frame, plan, "long", entry)) == [
        (entry, {"path_id": "rise", "children": {"rise": True}})
    ]


def test_anchor_not_ready_keeps_the_child_false(fixture_frame: Any) -> None:
    frame, plan, _, _ = fixture_frame
    series = _column(frame, "1h")
    entry = next(i for i, v in enumerate(series) if math.isfinite(v)) - 1
    assert entry >= 0 and not math.isfinite(series[entry])
    raw = _spec(_single(_rise("1h", ">=", -1000.0)))
    assert _transitions(_replay(raw, frame, plan, "long", entry)) == []


def test_side_relative_rise_with_di(fixture_frame: Any) -> None:
    """The rise is side-free; the DI child with its `short` override makes
    the path side-relative."""

    frame, plan, _, _ = fixture_frame
    raw = _spec(entry_change_case())
    series = _column(frame, "1h")
    plus = frame.series[
        next(f.output_id for f in parse_predicate(DI1H, "x").features() if f.kind == "di_plus")
    ]
    minus = frame.series[
        next(f.output_id for f in parse_predicate(DI1H, "x").features() if f.kind == "di_minus")
    ]
    checked = 0
    for side in ("long", "short"):
        for entry in range(150, len(frame.time_ms) - 1, 509):
            anchor = series[entry]
            expected = None
            if math.isfinite(anchor):
                for index in range(entry, len(series)):
                    p, m = plus[index], minus[index]
                    aligned = (
                        p is not None
                        and m is not None
                        and (
                            float(p) > float(m) if side == "long" else float(m) > float(p)
                        )
                    )
                    if math.isfinite(series[index]) and series[index] - anchor >= 2.0 and aligned:
                        expected = index
                        break
            got = _transitions(_replay(raw, frame, plan, side, entry))
            assert [bar for bar, _ in got] == ([] if expected is None else [expected]), (
                side,
                entry,
            )
            checked += expected is not None
    assert checked >= 10, checked


# -- explicit higher-timeframe entries between two closes (owner's ask) -------------


def test_htf_entry_between_closes_anchors_the_last_completed_bar(fixture_frame: Any) -> None:
    """A 1h operand on the 5m base, entries strictly inside an hour: the
    anchor is the last completed 1h bar at entry (not the forming one), the
    change is exactly 0 until the next 1h close, and every transition lands
    on a base bar where a new 1h bar has just completed."""

    frame, plan, _, _ = fixture_frame
    series = _column(frame, "1h")
    times = frame.time_ms
    up = _spec(_single(_rise("1h", ">", 0.0)))
    down = _spec(_single(_rise("1h", "<", 0.0)))
    entries = [
        i
        for i in range(300, len(times) - 300, 211)
        if times[i] % _HOUR_MS not in (0,) and math.isfinite(series[i])
    ]
    assert len(entries) >= 20
    fired = 0
    for entry in entries:
        hour_start = times[entry] - times[entry] % _HOUR_MS
        first_of_hour = times.index(hour_start)
        next_close = times.index(hour_start + _HOUR_MS)
        # The aligned 1h value at a mid-hour entry is the bar that closed at
        # the start of this hour; the forming hour is not visible.
        assert series[entry] == series[first_of_hour]
        assert all(series[i] == series[entry] for i in range(first_of_hour, next_close))
        for raw in (up, down):
            for side in ("long", "short"):
                got = _transitions(_replay(raw, frame, plan, side, entry))
                for bar, _ in got:
                    # Strictly after entry and only on an hour boundary.
                    assert bar >= next_close, (entry, bar)
                    assert times[bar] % _HOUR_MS == 0, (entry, bar)
                    fired += 1
    assert fired >= 20, fired


def test_htf_live_start_uses_the_same_anchor(fixture_frame: Any) -> None:
    """Offset 1 (live) starts at `entry + 1` with the anchor still at the
    entry bar: the first transition equals the offset 0 one whenever that
    one is after the entry bar."""

    from decimal import Decimal as D

    frame, plan, _, _ = fixture_frame
    raw = _spec(_single(_rise("1h", ">=", 1.0)))
    checked = 0
    for side in ("long", "short"):
        for entry in range(400, len(frame.time_ms) - 1, 733):
            want = _transitions(_replay(raw, frame, plan, side, entry))
            price = D(str(frame.market_bars[entry].open))
            stop, take = (
                (price * D("0.95"), price * D("1.1"))
                if side == "long"
                else (price * D("1.05"), price * D("0.9"))
            )
            live = evaluate_start_after_entry_managed_projection(
                raw,
                frame,
                plan,
                side=side,  # type: ignore[arg-type]
                entry_time_ms=frame.time_ms[entry],
                planned_entry_price=price,
                initial_stop_price=stop,
                initial_take_price=take,
                target_time_ms=frame.time_ms[-1],
            )
            got = _transitions(live.replay)
            if want and want[0][0] > entry:
                assert [bar for bar, _ in got] == [want[0][0]], (side, entry)
                checked += 1
    assert checked >= 5, checked


# -- 3.x projection shape and serialization ---------------------------------------


def test_projection_shape(fixture_frame: Any) -> None:
    frame, plan, _, _ = fixture_frame
    raw = _spec(entry_change_case(), entry_change_at_least(), to_phases=("proven", "runner"))
    projection = build_historical_managed_projection(raw, frame, plan)
    assert projection is not None
    first, second = projection.rules
    (path,) = first.paths  # type: ignore[attr-defined, misc]
    assert path.thresholds == ()
    assert path.condition_id is not None  # the DI predicate
    (change,) = path.entry_changes
    assert (change.op, change.value) == (">=", 2.0)
    series = projection.distances[change.series_id]
    expected = _column(frame, "1h")
    assert len(series) == len(expected)
    assert all(
        (math.isnan(a) and math.isnan(b)) or a == b for a, b in zip(series, expected, strict=True)
    )
    (vote,) = second.paths  # type: ignore[attr-defined, misc]
    assert vote.entry_changes == ()
    assert vote.at_least is not None and vote.at_least.k == 2
    kinds = [
        "entry"
        if t.entry_change is not None
        else ("market" if t.condition_id is not None else t.trade_metric)
        for t in vote.at_least.terms
    ]
    assert kinds == ["entry", "mfe_pct", "market"]

    wire = _serialize_path(path)
    assert wire["entry_changes"] == [{"series_id": change.series_id, "op": ">=", "value": 2.0}]
    vote_wire = _serialize_path(vote)
    assert "entry_changes" not in vote_wire
    terms = vote_wire["at_least"]["terms"]  # type: ignore[index]
    assert "entry_change" in terms[0] and "entry_change" not in terms[1]


def test_shared_child_emits_one_series(fixture_frame: Any) -> None:
    frame, plan, _, _ = fixture_frame
    condition = _composite(
        [_cond("rise", RISE_ADX1H), _pred("di1h", DI1H), _cond("pct", MFE_PCT)],
        [
            {"path_id": "a", "require": ["rise", "di1h"]},
            {"path_id": "b", "require": ["rise", "pct"]},
        ],
    )
    projection = build_historical_managed_projection(_spec(condition), frame, plan)
    assert projection is not None
    (rule,) = projection.rules
    ids = {path.entry_changes[0].series_id for path in rule.paths}  # type: ignore[union-attr]
    assert len(ids) == 1
    assert sum(key.endswith(":series") for key in projection.distances) == 1


def test_serialized_path_without_entry_changes_is_unchanged() -> None:
    from strategy_engine.strategies.contracts import (
        ManagedTransitionAtLeast,
        ManagedTransitionPath,
        ManagedTransitionTerm,
    )

    path = ManagedTransitionPath(
        "p",
        "c",
        (),
        ManagedTransitionAtLeast(1, (ManagedTransitionTerm("c", None, None),)),
    )
    assert _serialize_path(path) == {
        "path_id": "p",
        "condition_id": "c",
        "thresholds": [],
        "at_least": {
            "k": 1,
            "terms": [{"condition_id": "c", "distance_id": None, "trade_metric": None}],
        },
    }


# -- 4.x planning -------------------------------------------------------------------


def test_operand_is_planned_like_a_predicate_operand() -> None:
    plan = build_feature_plan_from_canonical_spec(_spec(_single(_rise("4h", ">=", 5.0))))
    labels = {feature.output_id for feature in plan.indicator_plan.features}
    expected = parse_change_since_entry(
        {"operand": _feature("adx", "4h"), "op": ">=", "value": 5.0}, "x"
    ).feature.output_id
    assert expected in labels


def test_live_history_is_an_explicit_zero_entry() -> None:
    requirements = EmaPullbackLiveCalculationRequirements().execute(
        _spec(_single(_rise("4h", ">=", 5.0)))
    )
    entries = [item for item in requirements if "change_since_entry" in item.reason]
    assert [(item.timeframe, item.bars) for item in entries] == [("base", 0)]
