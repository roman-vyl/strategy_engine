"""Band filter blocks (OpenSpec `a1-band-filter-v1`): `range` with optional bounds, bound mode and
empty policy; the `segment` and `ratio` operands; A1 end to end on a synthetic market."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.node_identity import node_spec
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.indicators.implementations.range_evaluator import (
    RangeIndicatorEvaluator,
    resolve_indicator_plan,
)
from strategy_engine.strategies.ema_pullback.predicates import (
    Range,
    column_node,
    evaluate_predicate,
    parse_predicate,
    resolve_predicate,
)

STEP_MS = 300_000


def _market_frame(count: int = 400, seed: int = 7) -> MarketFrame:
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0, 0.5, count))
    bars = tuple(
        MarketBar(
            index * STEP_MS,
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


RSI = {"kind": "rsi", "params": {"period": 14}}


def _range(**fields: Any) -> dict[str, Any]:
    return {"kind": "range", "operand": {"feature": RSI}, "min": 40, "max": 65, **fields}


def _rsi_column(mf: MarketFrame) -> tuple[Any, np.ndarray]:
    predicate = parse_predicate(_range(), "p")
    features = predicate.features()
    frame = RangeIndicatorEvaluator().evaluate_native(mf, IndicatorPlan("1", features))
    column = np.array(
        [np.nan if v is None else v for v in frame.series[features[0].output_id]], dtype=float
    )
    return frame, column


# -- range: parsing -------------------------------------------------------------


def test_existing_range_parses_with_defaults() -> None:
    predicate = parse_predicate(_range(), "p")
    assert isinstance(predicate.long, Range)
    assert (predicate.long.min, predicate.long.max) == (40.0, 65.0)
    assert (predicate.long.bounds, predicate.long.empty) == ("inclusive", "block")


def test_null_sides_are_accepted() -> None:
    both = parse_predicate(_range(min=None, max=None), "p")
    assert isinstance(both.long, Range)
    assert (both.long.min, both.long.max) == (None, None)
    low_only = parse_predicate(_range(max=None, bounds="exclusive", empty="pass"), "p")
    assert isinstance(low_only.long, Range)
    assert (low_only.long.min, low_only.long.max) == (40.0, None)


@pytest.mark.parametrize(
    "mutation",
    [
        {"bounds": "open"},
        {"bounds": None},
        {"empty": "allow"},
        {"empty": True},
        {"bounds": "exclusive", "min": 50, "max": 50},
        {"min": 70, "max": 60},
        {"min": float("nan")},
        {"max": float("inf")},
        {"min": "1"},
        {"min": True},
        {"extra": 1},
    ],
)
def test_invalid_range_is_rejected(mutation: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequestError):
        parse_predicate(_range(**mutation), "p")


@pytest.mark.parametrize("missing", ["min", "max"])
def test_a_bound_key_must_be_present(missing: str) -> None:
    raw = _range()
    del raw[missing]
    with pytest.raises(InvalidRequestError):
        parse_predicate(raw, "p")


def test_inclusive_range_may_have_equal_bounds() -> None:
    parse_predicate(_range(min=50, max=50), "p")


def test_short_override_may_replace_bounds_and_policies() -> None:
    predicate = parse_predicate(
        _range(short={"min": None, "max": 30, "bounds": "exclusive", "empty": "pass"}), "p"
    )
    short = predicate.for_side("short")
    assert isinstance(short, Range)
    assert (short.min, short.max, short.bounds, short.empty) == (None, 30.0, "exclusive", "pass")
    with pytest.raises(InvalidRequestError):
        parse_predicate(_range(short={"operand": {"price": "close"}}), "p")


# -- range: evaluation ----------------------------------------------------------


@pytest.mark.parametrize("bounds", ["inclusive", "exclusive"])
@pytest.mark.parametrize("empty", ["block", "pass"])
@pytest.mark.parametrize(
    ("low", "high"), [(40, 65), (40, None), (None, 65), (None, None), (50.0, 50.0)]
)
def test_range_matches_a_reference(
    bounds: str, empty: str, low: float | None, high: float | None
) -> None:
    if bounds == "exclusive" and low is not None and low == high:
        pytest.skip("rejected by validation")
    mf = _market_frame()
    frame, column = _rsi_column(mf)
    raw = _range(min=low, max=high, bounds=bounds, empty=empty)
    mask = evaluate_predicate(parse_predicate(raw, "p"), frame, "long")
    expected = np.ones(len(column), dtype=bool)
    finite = np.isfinite(column)
    for i, value in enumerate(column):
        if not finite[i]:
            expected[i] = empty == "pass"
            continue
        ok = True
        if low is not None:
            ok &= value > low if bounds == "exclusive" else value >= low
        if high is not None:
            ok &= value < high if bounds == "exclusive" else value <= high
        expected[i] = ok
    assert np.array_equal(mask, expected)
    assert (~finite).any(), "fixture must contain warm-up bars"


def test_both_sliders_off_pass_everything_with_empty_pass() -> None:
    frame, _ = _rsi_column(_market_frame())
    mask = evaluate_predicate(
        parse_predicate(_range(min=None, max=None, empty="pass"), "p"), frame, "long"
    )
    assert mask.all()


def test_both_sliders_off_default_empty_blocks_only_missing() -> None:
    frame, column = _rsi_column(_market_frame())
    mask = evaluate_predicate(parse_predicate(_range(min=None, max=None), "p"), frame, "long")
    assert np.array_equal(mask, np.isfinite(column))


def test_exclusive_bound_excludes_the_equal_value() -> None:
    frame, column = _rsi_column(_market_frame())
    pivot = float(column[np.isfinite(column)][10])
    inclusive = evaluate_predicate(
        parse_predicate(_range(min=pivot, max=None), "p"), frame, "long"
    )
    exclusive = evaluate_predicate(
        parse_predicate(_range(min=pivot, max=None, bounds="exclusive"), "p"), frame, "long"
    )
    index = int(np.flatnonzero(column == pivot)[0])
    assert inclusive[index] and not exclusive[index]


# -- range: identity ------------------------------------------------------------


def test_existing_range_identity_is_unchanged() -> None:
    predicate = parse_predicate(_range(), "p")
    features = predicate.features()
    ids = resolve_indicator_plan(IndicatorPlan("1", features), base_timeframe="5m")
    identity = resolve_predicate(predicate, ids, "long")
    expected = node_spec(
        "predicate.range",
        version=1,
        params={"operand": ("feature",), "min": 40.0, "max": 65.0},
        upstream={"operand": column_node(ids[features[0].output_id])},
        side=None,
    )
    assert identity.local == expected


def test_band_settings_enter_the_identity_only_when_not_default() -> None:
    features = parse_predicate(_range(), "p").features()
    ids = resolve_indicator_plan(IndicatorPlan("1", features), base_timeframe="5m")

    def local(**fields: Any) -> Any:
        return resolve_predicate(parse_predicate(_range(**fields), "p"), ids, "long").local

    base = local()
    assert local(bounds="inclusive", empty="block") == base
    assert len({base, local(bounds="exclusive"), local(empty="pass"), local(max=None)}) == 4
