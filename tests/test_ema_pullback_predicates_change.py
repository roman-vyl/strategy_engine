"""Predicate class `change` (OpenSpec `predicate-change-class-v1`): parsing, per-bar semantics
against an independent reference on the real evaluator and its real higher-timeframe alignment
(design D2), side override, windows, identity and live history."""

from __future__ import annotations

import operator
from decimal import Decimal
from typing import Any

import numpy as np
import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.node_identity import node_spec
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    _predicate_history,
)
from strategy_engine.strategies.ema_pullback.predicates import (
    Change,
    evaluate_predicate,
    parse_predicate,
    resolve_predicate,
)

STEP_MS = 300_000
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def _market_frame(start_row: int, count: int, seed: int) -> MarketFrame:
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0, 0.5, count))
    bars = tuple(
        MarketBar(
            (start_row + index) * STEP_MS,
            Decimal(str(price[index])),
            Decimal(str(price[index] + abs(rng.normal(0, 0.4)))),
            Decimal(str(price[index] - abs(rng.normal(0, 0.4)))),
            Decimal(str(price[index] + rng.normal(0, 0.1))),
            Decimal("1"),
        )
        for index in range(count)
    )
    return MarketFrame(
        MarketStream("BTCUSDT.P", "5m"),
        TimeRange(bars[0].open_time_ms, bars[-1].open_time_ms + STEP_MS),
        bars,
        "fixture-hash",
    )


def _feature(kind: str, period: int, timeframe: str | None = None) -> dict[str, Any]:
    feature: dict[str, Any] = {"kind": kind, "params": {"period": period}}
    if timeframe is not None:
        feature["timeframe"] = timeframe
    return feature


def _change(
    timeframe: str | None = None,
    lookback: int = 2,
    op: str = ">=",
    value: float = 0.5,
    kind: str = "ema",
    period: int = 5,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "kind": "change",
        "operand": {"feature": _feature(kind, period, timeframe)},
        "lookback": lookback,
        "op": op,
        "value": value,
        **extra,
    }


def _evaluate(
    raw: dict[str, Any], mf: MarketFrame, side: str = "long"
) -> tuple[np.ndarray, np.ndarray]:
    predicate = parse_predicate(raw, "p")
    features = predicate.features()
    frame = RangeIndicatorEvaluator().evaluate_native(mf, IndicatorPlan("1", features))
    column = np.array(
        [np.nan if v is None else v for v in frame.series[features[0].output_id]], dtype=float
    )
    return evaluate_predicate(predicate, frame, side), column


# -- parsing ------------------------------------------------------------------


def test_parses_a_valid_change() -> None:
    predicate = parse_predicate(_change("1h", 3, "<=", -1.5), "p")
    assert isinstance(predicate.long, Change)
    assert (predicate.long.lookback, predicate.long.op, predicate.long.value) == (3, "<=", -1.5)
    assert predicate.short is None


@pytest.mark.parametrize(
    "mutation",
    [
        {"lookback": 0},
        {"lookback": -1},
        {"lookback": 1.5},
        {"lookback": True},
        {"lookback": "3"},
        {"op": "=="},
        {"op": "!="},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": "1"},
        {"value": True},
        {"operand": {"price": "close"}},
        {"operand": {"const": 1}},
        {"extra": 1},
        {"short": {}},
        {"short": {"lookback": 4}},
        {"short": {"operand": {"feature": _feature("ema", 9)}}},
    ],
)
def test_invalid_change_is_rejected(mutation: dict[str, Any]) -> None:
    raw = {**_change(), **mutation}
    with pytest.raises(InvalidRequestError):
        parse_predicate(raw, "p")


def test_short_override_may_replace_op_and_value_only() -> None:
    predicate = parse_predicate(_change(short={"op": "<=", "value": -0.5}), "p")
    assert predicate.for_side("short") == Change(
        predicate.long.operand,
        2,
        "<=",
        -0.5,  # type: ignore[union-attr]
    )
    assert predicate.for_side("long").op == ">="  # type: ignore[union-attr]


def test_operand_feature_is_validated_by_the_feature_contract() -> None:
    raw = {**_change(), "operand": {"feature": {"kind": "no_such_kind", "params": {}}}}
    with pytest.raises(InvalidRequestError):
        parse_predicate(raw, "p")


# -- evaluation ---------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(OPS))
@pytest.mark.parametrize("lookback", [1, 3])
def test_base_timeframe_matches_a_naive_reference(op: str, lookback: int) -> None:
    mf = _market_frame(0, 600, seed=1)
    mask, column = _evaluate(_change(None, lookback, op, 0.3), mf)
    expected = np.zeros(len(column), dtype=bool)
    for i in range(lookback, len(column)):
        a, b = column[i], column[i - lookback]
        expected[i] = bool(np.isfinite(a) and np.isfinite(b) and OPS[op](a - b, 0.3))
    assert np.array_equal(mask, expected)
    assert mask.any() and not mask.all()


@pytest.mark.parametrize("start_row", [0, 1, 7, 47, 143])
@pytest.mark.parametrize("tf", ["15m", "1h", "4h"])
@pytest.mark.parametrize("lookback", [1, 2, 5])
def test_higher_timeframe_counts_bars_of_that_timeframe(
    start_row: int, tf: str, lookback: int
) -> None:
    """Design D2: the value of completed feature bar j is read where bar j first becomes visible;
    the predicate must equal the difference of bars j and j - lookback computed from bucket
    indices, on every base bar."""

    mf = _market_frame(start_row, 2051, seed=start_row + lookback)
    mask, aligned = _evaluate(_change(tf, lookback, ">", 0.0, "rsi", 4), mf)
    times = np.array([bar.open_time_ms for bar in mf.bars])
    bucket = times // TF_MS[tf]
    value: dict[int, float] = {}
    for i in range(len(times)):
        if i == 0 or bucket[i] != bucket[i - 1]:
            value[int(bucket[i]) - 1] = aligned[i]
    expected = np.zeros(len(times), dtype=bool)
    for i in range(len(times)):
        j = int(bucket[i]) - 1
        a, b = value.get(j, np.nan), value.get(j - lookback, np.nan)
        expected[i] = bool(np.isfinite(a) and np.isfinite(b) and a - b > 0.0)
    # the value of bar j is only observable from the second bucket on; compare where the
    # reference is defined, and require False before the first two points exist
    defined = np.array([int(bucket[i]) - 1 in value for i in range(len(times))])
    assert np.array_equal(mask[defined], expected[defined])
    first_visible = int(np.argmax(np.isfinite(aligned)))
    assert not mask[: first_visible + lookback * (TF_MS[tf] // STEP_MS)].any()
    assert mask.any()


def test_non_finite_and_start_of_frame_are_false() -> None:
    mf = _market_frame(0, 300, seed=2)
    mask, column = _evaluate(_change(None, 4, ">=", -1e9), mf)
    assert not mask[:4].any()
    assert np.array_equal(mask[4:], np.isfinite(column[4:]) & np.isfinite(column[:-4]))


def test_lookback_longer_than_the_frame_is_all_false() -> None:
    mf = _market_frame(0, 50, seed=3)
    mask, _ = _evaluate(_change(None, 80, ">=", -1e9), mf)
    assert not mask.any()


def test_short_override_changes_the_condition_for_short_only() -> None:
    mf = _market_frame(0, 600, seed=4)
    raw = _change(None, 2, ">=", 0.3, short={"op": "<=", "value": -0.3})
    long_mask, column = _evaluate(raw, mf, "long")
    short_mask, _ = _evaluate(raw, mf, "short")
    diff = column[2:] - column[:-2]
    assert np.array_equal(long_mask[2:], np.isfinite(diff) & (diff >= 0.3))
    assert np.array_equal(short_mask[2:], np.isfinite(diff) & (diff <= -0.3))
    assert not (long_mask & short_mask).any()


def test_side_free_change_is_identical_for_both_sides() -> None:
    mf = _market_frame(0, 400, seed=5)
    raw = _change(None, 3, ">", 0.0)
    assert np.array_equal(_evaluate(raw, mf, "long")[0], _evaluate(raw, mf, "short")[0])


@pytest.mark.parametrize("mode", ["held_for", "within"])
def test_temporal_windows_over_change(mode: str) -> None:
    mf = _market_frame(0, 600, seed=6)
    inner, _ = _evaluate(_change(None, 2, ">", 0.0), mf)
    temporal = {"kind": "temporal", "mode": mode, "bars": 4, "of": _change(None, 2, ">", 0.0)}
    mask, _ = _evaluate(temporal, mf)
    expected = np.zeros(len(inner), dtype=bool)
    for i in range(len(inner)):
        window = inner[max(0, i - 3) : i + 1]
        if mode == "held_for":
            expected[i] = i >= 3 and bool(window.all())
        else:
            expected[i] = bool(window.any())
    assert np.array_equal(mask, expected)


def test_evaluation_is_deterministic() -> None:
    mf = _market_frame(3, 500, seed=7)
    raw = _change("1h", 2, ">=", 1.0, "rsi", 4)
    assert np.array_equal(_evaluate(raw, mf)[0], _evaluate(raw, mf)[0])


def test_operand_timeframe_must_be_an_integral_multiple_of_the_base() -> None:
    mf = _market_frame(0, 200, seed=8)
    with pytest.raises(InvalidRequestError):
        _evaluate(_change("7m", 1, ">", 0.0), mf)


# -- identity -----------------------------------------------------------------


def _identity(raw: dict[str, Any], side: str = "long"):
    predicate = parse_predicate(raw, "p")
    feature_ids = {
        f.output_id: node_spec("feature.test", version=1, params={"label": f.output_id})
        for f in predicate.features()
    }
    return resolve_predicate(predicate, feature_ids, side)


def test_change_identity_is_side_free_without_override_and_shares_its_column() -> None:
    a = _identity(_change("1h", 3, ">=", 1.0))
    b = _identity(_change("1h", 3, ">=", 2.0))
    assert a.local.kind == "predicate.change"
    assert a.local.side is None
    assert a.local != b.local
    assert a.nested == b.nested and a.column_ids == b.column_ids


def test_change_identity_carries_side_only_with_an_override() -> None:
    raw = _change("1h", 3, ">=", 1.0, short={"op": "<=", "value": -1.0})
    assert _identity(raw, "long").local.side == "long"
    assert _identity(raw, "short").local.side == "short"
    assert _identity(_change("1h", 3), "long").local != _identity(_change("1h", 4), "long").local


# -- live history -------------------------------------------------------------


def _history(raw: dict[str, Any]) -> tuple[str, int]:
    (requirement,) = _predicate_history(parse_predicate(raw, "p"), "child")
    return requirement.timeframe, requirement.bars


def test_history_for_change_is_lookback_bars_of_the_operand_timeframe() -> None:
    assert _history(_change(None, 5)) == ("base", 5)
    assert _history(_change("1h", 3)) == ("1h", 3)


def test_history_for_a_window_over_change_is_a_sufficient_bound() -> None:
    raw = {"kind": "temporal", "mode": "held_for", "bars": 12, "of": _change("1h", 3)}
    assert _history(raw) == ("1h", 14)


def test_history_of_current_bar_predicates_is_unchanged() -> None:
    compare = {
        "kind": "compare",
        "left": {"feature": _feature("rsi", 14)},
        "op": "<",
        "right": {"const": 70},
    }
    assert _history(compare) == ("base", 0)
    windowed = {"kind": "temporal", "mode": "within", "bars": 6, "of": compare}
    assert _history(windowed) == ("base", 5)
