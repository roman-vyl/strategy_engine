"""Band filter blocks (OpenSpec `a1-band-filter-v1`): `range` with optional bounds, bound mode and
empty policy; the `segment` and `ratio` operands; A1 end to end on a synthetic market."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from test_ema_pullback_stack_episode import _project

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
    Segment,
    SegmentSeries,
    column_node,
    evaluate_predicate,
    parse_predicate,
    resolve_predicate,
    segment_values,
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


# -- segment: parsing -----------------------------------------------------------

EMA5 = {"kind": "ema", "params": {"period": 5}}
EMA200 = {"kind": "ema", "params": {"period": 200}}


def _segment(**fields: Any) -> dict[str, Any]:
    return {
        "episode": "trend",
        "of": {"difference": {"left": EMA5, "right": EMA200}},
        "from": "peak",
        "to": "current",
        "aggregate": "mean_per_bar",
        **fields,
    }


def _seg_range(operand: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {"kind": "range", "operand": operand, "min": 0.9, "max": None, **fields}


def test_valid_segment_parses_and_plans_both_series() -> None:
    raw = _seg_range(
        {"segment": _segment(value="change", window={"last_n": 75}, negate=True)},
        bounds="exclusive",
        empty="pass",
    )
    predicate = parse_predicate(raw, "p", episode_refs=["trend"])
    assert isinstance(predicate.long, Range)
    segment = predicate.long.operand.segment
    assert segment is not None
    assert (segment.start, segment.end, segment.value, segment.last_n, segment.negate) == (
        "peak",
        "current",
        "change",
        75,
        True,
    )
    assert [f.output_id for f in predicate.features()] == [
        f.output_id for f in segment.series.features()
    ]
    assert len(predicate.features()) == 2


def test_segment_defaults() -> None:
    segment = parse_predicate(_seg_range({"segment": _segment()}), "p").long.operand.segment  # type: ignore[union-attr]
    assert segment is not None
    assert (segment.value, segment.last_n, segment.negate) == ("level", None, False)
    single = parse_predicate(_seg_range({"segment": _segment(of=RSI)}), "p")
    assert len(single.features()) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        {"episode": ""},
        {"episode": "other"},
        {"from": "current", "to": "peak"},
        {"from": "peak", "to": "peak"},
        {"from": "origin", "to": "touch"},
        {"aggregate": "max"},
        {"aggregate": "mean"},
        {"value": "delta"},
        {"window": {"last_n": 0}},
        {"window": {"last_n": 1.5}},
        {"window": {"last_n": True}},
        {"window": {"top_fraction": 0.5}},
        {"window": 75},
        {"negate": 1},
        {"select": "positive"},
        {"of": {"difference": {"left": EMA5}}},
        {"of": {"difference": {"left": EMA5, "right": EMA200, "extra": 1}}},
        {"of": {"kind": "ema", "params": {"period": 0}}},
    ],
)
def test_invalid_segment_is_rejected(mutation: dict[str, Any]) -> None:
    raw = _seg_range({"segment": _segment(**mutation)})
    with pytest.raises(InvalidRequestError):
        parse_predicate(raw, "p", episode_refs=["trend"])


@pytest.mark.parametrize("missing", ["episode", "of", "from", "to", "aggregate"])
def test_segment_required_fields(missing: str) -> None:
    segment = _segment()
    del segment[missing]
    with pytest.raises(InvalidRequestError):
        parse_predicate(_seg_range({"segment": segment}), "p")


def test_segment_is_not_a_change_operand_and_not_a_short_override() -> None:
    change = {
        "kind": "change",
        "operand": {"segment": _segment()},
        "lookback": 2,
        "op": ">",
        "value": 0,
    }
    with pytest.raises(InvalidRequestError):
        parse_predicate(change, "p")
    compare = {
        "kind": "compare",
        "left": {"feature": RSI},
        "op": ">",
        "right": {"const": 1},
        "short": {"left": {"segment": _segment()}},
    }
    with pytest.raises(InvalidRequestError):
        parse_predicate(compare, "p")


def test_ratio_parsing() -> None:
    segment = {"segment": _segment()}
    ok = parse_predicate(_seg_range({"ratio": {"left": segment, "right": segment}}), "p")
    assert len(ok.features()) == 4
    for ratio in (
        {"left": segment},
        {"left": {"const": 1}, "right": {"const": 2}},
        {"left": {"ratio": {"left": segment, "right": segment}}, "right": segment},
        {"left": segment, "right": segment, "extra": 1},
    ):
        with pytest.raises(InvalidRequestError):
            parse_predicate(_seg_range({"ratio": ratio}), "p")


# -- ratio on plain operands ----------------------------------------------------


@pytest.mark.parametrize(("denominator", "empty"), [(0, "pass"), (0, "block"), (-2, "pass")])
def test_ratio_is_missing_for_a_non_positive_denominator(denominator: float, empty: str) -> None:
    frame, _ = _rsi_column(_market_frame())
    raw = _seg_range(
        {"ratio": {"left": {"price": "close"}, "right": {"const": denominator}}},
        min=None,
        max=None,
        empty=empty,
    )
    mask = evaluate_predicate(parse_predicate(raw, "p"), frame, "long")
    assert mask.all() == (empty == "pass")
    assert mask.any() == (empty == "pass")


def test_ratio_value_is_left_over_right() -> None:
    frame, column = _rsi_column(_market_frame())
    raw = {
        "kind": "compare",
        "left": {"ratio": {"left": {"feature": RSI}, "right": {"const": 4}}},
        "op": ">",
        "right": {"const": 12.5},
    }
    mask = evaluate_predicate(parse_predicate(raw, "p"), frame, "long")
    with np.errstate(invalid="ignore"):
        assert np.array_equal(mask, np.isfinite(column) & (column / 4 > 12.5))


# -- segment: values against a brute-force reference ----------------------------

# Several touches in one episode (window 3): wave rows with origin, peak and touch bars.
_SHAPE = "X" + "UUUCUU" * 6 + "UC" + "UUUU"


def _reference(episode: Any, x: np.ndarray, segment: Segment) -> np.ndarray:
    state, touches = episode.state, episode.touches
    out = np.full(len(x), np.nan)
    for t in range(len(x)):
        number = state["touch_number"][t]
        if not np.isfinite(number) or number < 1:
            continue
        row = int(episode.first_row[int(state["episode_id"][t])]) + int(number) - 1
        points = {
            "origin": int(touches["origin_bar"][row]),
            "peak": int(touches["peak_bar"][row]),
            "current": t,
        }
        a, e = points[segment.start], points[segment.end]
        s = a if segment.last_n is None else max(a, e - segment.last_n + 1)
        if segment.value == "level":
            values = x[s : e + 1]
        else:
            if s - 1 < 0:
                continue
            values = np.diff(x[s - 1 : e + 1])
        if not np.isfinite(values).all():
            continue
        total = float(np.sum(values))
        result = total if segment.aggregate == "sum" else total / (e - s + 1)
        out[t] = -result if segment.negate else result
    return out


def _segment_args(**fields: Any) -> Segment:
    base: dict[str, Any] = {
        "episode": "trend",
        "series": SegmentSeries(parse_predicate(_range(), "p").features()[0]),
        "start": "peak",
        "end": "current",
        "aggregate": "mean_per_bar",
    }
    return Segment(**{**base, **fields})


@pytest.mark.parametrize(
    "start_end", [("origin", "peak"), ("peak", "current"), ("origin", "current")]
)
@pytest.mark.parametrize("value", ["level", "change"])
@pytest.mark.parametrize("last_n", [None, 1, 2, 5, 500])
@pytest.mark.parametrize("aggregate", ["sum", "mean_per_bar"])
@pytest.mark.parametrize("negate", [False, True])
def test_segment_matches_the_reference(
    start_end: tuple[str, str], value: str, last_n: int | None, aggregate: str, negate: bool
) -> None:
    episode = _project(_SHAPE, window=3)
    rng = np.random.default_rng(3)
    x = np.cumsum(rng.normal(0, 1, len(_SHAPE)))
    segment = _segment_args(
        start=start_end[0], end=start_end[1], value=value, last_n=last_n,
        aggregate=aggregate, negate=negate,
    )
    got = segment_values(episode, x, segment)
    expected = _reference(episode, x, segment)
    assert np.isfinite(expected).sum() > 10
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=1e-12, equal_nan=True)
    assert not got.flags.writeable


def test_segment_is_missing_when_a_value_it_reads_is_not_finite() -> None:
    episode = _project(_SHAPE, window=3)
    x = np.arange(len(_SHAPE), dtype=float)
    x[10] = np.nan
    for value in ("level", "change"):
        segment = _segment_args(start="origin", end="current", value=value)
        got = segment_values(episode, x, segment)
        np.testing.assert_allclose(
            got, _reference(episode, x, segment), equal_nan=True, rtol=1e-12
        )
        assert np.isnan(got[10])
    # the value read by `change` at bar 10 also covers bar 11 (x[11] - x[10])
    change_segment = _segment_args(start="origin", end="current", value="change")
    change = segment_values(episode, x, change_segment)
    assert np.isnan(change[11])


def test_segment_is_missing_before_a_touch_and_without_an_episode() -> None:
    episode = _project("XUUU" + "UUUU", window=3)
    got = segment_values(episode, np.arange(8, dtype=float), _segment_args())
    assert np.isnan(got).all()
    none = _project("UUUU", window=3)
    assert np.isnan(segment_values(none, np.arange(4, dtype=float), _segment_args())).all()


def test_segment_uses_only_bars_up_to_the_evaluated_bar() -> None:
    episode = _project(_SHAPE, window=3)
    rng = np.random.default_rng(5)
    x = rng.normal(0, 1, len(_SHAPE))
    segment = _segment_args(start="origin", end="current", value="change", last_n=4)
    full = segment_values(episode, x, segment)
    for cut in (20, 30, 40):
        y = x.copy()
        y[cut + 1 :] = rng.normal(0, 100, len(y) - cut - 1)
        changed = segment_values(episode, y, segment)
        np.testing.assert_array_equal(full[: cut + 1], changed[: cut + 1])
