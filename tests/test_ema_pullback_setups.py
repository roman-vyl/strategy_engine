from __future__ import annotations

import math
import random
from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
)
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.setups import (
    _anchor_stack_width,
    _combine_setup_masks,
    _untouched_anchor,
    evaluate_setups,
)


def raw_spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long"]},
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [{"instance_id": "none", "component_id": "no_blockers"}],
        },
        "setups": [
            {
                "instance_id": "untouched",
                "component_id": "untouched_anchor_setup",
                "params": {"lookback": 2, "active_bars": 2},
            },
            {
                "instance_id": "bounce",
                "component_id": "ema_bounce_counter_setup",
                "params": {
                    "max_bounces": 2,
                    "raw_touch_mode": "range_cross",
                    "touch_lookback_bars": 2,
                    "trend_start_confirmation_bars": 1,
                    "trend_break_confirmation_bars": 1,
                },
            },
            {
                "instance_id": "width",
                "component_id": "anchor_stack_width_setup",
                "params": {
                    "atr_timeframe": "base",
                    "atr_period": 2,
                    "min_current_width_atr": 1.0,
                    "min_recent_width_atr": 1.0,
                    "width_lookback_bars": 2,
                },
            },
        ],
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


def feature_frame() -> FeatureFrame:
    time_ms = tuple(index * 300_000 for index in range(7))
    opens = ("5", "6", "7", "8", "9", "8", "10")
    closes = ("6", "7", "8", "9", "8", "10", "11")
    lows = ("4", "5", "6", "6.5", "7", "7", "9")
    highs = ("7", "8", "9", "10", "10", "11", "12")
    bars = tuple(
        MarketBar(
            timestamp,
            Decimal(open_value),
            Decimal(high_value),
            Decimal(low_value),
            Decimal(close_value),
            Decimal("1"),
        )
        for timestamp, open_value, high_value, low_value, close_value in zip(
            time_ms, opens, highs, lows, closes, strict=True
        )
    )
    return FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, len(time_ms) * 300_000),
        time_ms=time_ms,
        series={
            "ema_close_base_2": ("6", "7", "8", "9", "9", "10", "11"),
            "ema_close_base_3": ("5", "6", "7", "8", "8", "9", "10"),
            "ema_close_base_5": ("4", "5", "6", "7", "7", "8", "9"),
            "atr_close_base_2": (None, "1", "1", "1", "1", "1", "1"),
        },
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=bars,
    )


def test_setups_are_and_composed_after_direction_and_blockers() -> None:
    spec = raw_spec()
    frame = feature_frame()
    plan = build_feature_plan_from_canonical_spec(spec)
    prior = evaluate_direction_and_blockers(spec, frame, plan, ())
    output = evaluate_setups(spec, frame, plan, (), prior)[0]
    assert [item.component_id for item in output.setups] == [
        "untouched_anchor_setup",
        "ema_bounce_counter_setup",
        "anchor_stack_width_setup",
    ]
    assert output.setups_ok == tuple(
        all(item.final_setup_allowed[index] for item in output.setups)
        for index in range(len(frame.time_ms))
    )
    assert output.pre_trigger_allowed == tuple(
        left and right
        for left, right in zip(prior[0].pre_setup_allowed, output.setups_ok, strict=True)
    )


def test_setup_context_gate_is_applied_after_local_semantics() -> None:
    spec = raw_spec()
    setup = spec["setups"][0]  # type: ignore[index]
    setup["context_consumption"] = {  # type: ignore[index]
        "context_ref": "htf",
        "policy": {
            "policy_id": "htf_regime_gate",
            "params": {"allowed_regimes": ["aligned"]},
        },
    }
    frame = feature_frame()
    plan = build_feature_plan_from_canonical_spec(spec)
    prior = evaluate_direction_and_blockers(spec, frame, plan, ())
    gate = (True, False, True, False, True, False, True)
    record = ContextConsumptionRecord(
        role="setup",
        context_ref="htf",
        policy_id="htf_regime_gate",
        side="long",
        component_id="untouched_anchor_setup",
        instance_id="untouched",
        raw_state=("up",) * len(gate),
        allowed=gate,
        allowed_regimes=("aligned",),
    )
    result = evaluate_setups(spec, frame, plan, (record,), prior)[0].setups[0]
    assert result.final_setup_allowed == tuple(
        left and right for left, right in zip(result.local_setup_allowed, gate, strict=True)
    )


def _plain_frame(
    *, closes: tuple[str, ...], series: dict[str, tuple[str | None, ...]]
) -> FeatureFrame:
    time_ms = tuple(index * 300_000 for index in range(len(closes)))
    bars = tuple(
        MarketBar(
            timestamp,
            Decimal(close_value),
            Decimal(close_value),
            Decimal(close_value),
            Decimal(close_value),
            Decimal("1"),
        )
        for timestamp, close_value in zip(time_ms, closes, strict=True)
    )
    return FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, len(time_ms) * 300_000),
        time_ms=time_ms,
        series=series,
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=bars,
    )


def _untouched_anchor_frame(
    *,
    close: tuple[float, ...],
    low: tuple[float, ...],
    high: tuple[float, ...],
    anchor: tuple[float, ...],
) -> FeatureFrame:
    n = len(close)
    time_ms = tuple(index * 300_000 for index in range(n))
    bars = tuple(
        MarketBar(
            timestamp,
            Decimal(str(low[index])),
            Decimal(str(high[index])),
            Decimal(str(low[index])),
            Decimal(str(close[index])),
            Decimal("1"),
        )
        for index, timestamp in enumerate(time_ms)
    )
    return FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, n * 300_000),
        time_ms=time_ms,
        series={"anchor": tuple(str(v) for v in anchor)},
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=bars,
    )


# ---- reference (pre-vectorization) implementations, kept only for parity assertions ----


def _untouched_prior_reference(touch: tuple[bool, ...], lookback: int) -> tuple[bool, ...]:
    out: list[bool] = []
    for index in range(len(touch)):
        if index < lookback:
            out.append(False)
            continue
        out.append(not any(touch[index - lookback : index]))
    return tuple(out)


def _touch_active_reference(first_touch: tuple[bool, ...], active_bars: int) -> tuple[bool, ...]:
    return tuple(
        any(first_touch[max(0, index - active_bars + 1) : index + 1])
        for index in range(len(first_touch))
    )


def _recent_max_reference(width_atr: tuple[float, ...], lookback: int) -> tuple[float, ...]:
    recent_max: list[float] = []
    for index in range(len(width_atr)):
        window = width_atr[index - lookback + 1 : index + 1] if index + 1 >= lookback else ()
        recent = max(window) if window and all(math.isfinite(v) for v in window) else float("nan")
        recent_max.append(recent)
    return tuple(recent_max)


def _setups_ok_reference(
    masks_allowed: tuple[tuple[bool, ...], ...], length: int
) -> tuple[bool, ...]:
    if not masks_allowed:
        return tuple(True for _ in range(length))
    return tuple(all(mask[index] for mask in masks_allowed) for index in range(length))


def _nan_aware_equal(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b, strict=True):
        if math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


# ---- untouched_prior / touch_active parity (via _untouched_anchor) ----


def test_untouched_prior_and_touch_active_parity_edge_cases() -> None:
    cases = [
        (False,) * 10,
        (True,) * 10,
        (True, False, True, False, True, False, True, False, True, False),
        (False, False, False, True, False, False, False, False, False, False),
        (True,) + (False,) * 9,
    ]
    for touch_pattern in cases:
        for lookback in (1, 2, 3, 5, 10):
            for active_bars in (1, 2, 3):
                # Build a frame whose touch series (low<=anchor for long) equals touch_pattern
                # exactly, and side_ok is always True so armed_pre depends only on
                # untouched_prior/touch, isolating the fragments under test.
                n = len(touch_pattern)
                anchor = tuple(5.0 for _ in range(n))
                low = tuple(4.0 if touched else 6.0 for touched in touch_pattern)
                high = tuple(6.0 for _ in range(n))
                close = tuple(10.0 for _ in range(n))
                frame = _untouched_anchor_frame(close=close, low=low, high=high, anchor=anchor)
                params = {"lookback": lookback, "active_bars": active_bars}
                _, trace = _untouched_anchor(frame, "anchor", params, "long")
                expected_untouched_prior = _untouched_prior_reference(touch_pattern, lookback)
                assert trace["untouched_prior"] == expected_untouched_prior
                expected_first_touch = tuple(
                    touched and untouched
                    for touched, untouched in zip(
                        touch_pattern, expected_untouched_prior, strict=True
                    )
                )
                expected_touch_active = _touch_active_reference(expected_first_touch, active_bars)
                assert trace["touch_active"] == expected_touch_active


def test_untouched_prior_and_touch_active_parity_random() -> None:
    rng = random.Random(1234)
    for _ in range(50):
        n = rng.randint(1, 60)
        touch_pattern = tuple(rng.random() < 0.5 for _ in range(n))
        lookback = rng.randint(1, n + 5)
        active_bars = rng.randint(1, n + 5)
        anchor = tuple(5.0 for _ in range(n))
        low = tuple(4.0 if touched else 6.0 for touched in touch_pattern)
        high = tuple(6.0 for _ in range(n))
        close = tuple(10.0 for _ in range(n))
        frame = _untouched_anchor_frame(close=close, low=low, high=high, anchor=anchor)
        params = {"lookback": lookback, "active_bars": active_bars}
        _, trace = _untouched_anchor(frame, "anchor", params, "long")
        expected_untouched_prior = _untouched_prior_reference(touch_pattern, lookback)
        assert trace["untouched_prior"] == expected_untouched_prior
        expected_first_touch = tuple(
            touched and untouched
            for touched, untouched in zip(touch_pattern, expected_untouched_prior, strict=True)
        )
        expected_touch_active = _touch_active_reference(expected_first_touch, active_bars)
        assert trace["touch_active"] == expected_touch_active


def test_untouched_prior_first_and_last_bar() -> None:
    # First bar: index 0 < any lookback >= 1 -> untouched_prior[0] is always False.
    touch_pattern = (True, False, False, False, True)
    frame = _untouched_anchor_frame(
        close=(10.0,) * 5,
        low=tuple(4.0 if t else 6.0 for t in touch_pattern),
        high=(6.0,) * 5,
        anchor=(5.0,) * 5,
    )
    _, trace = _untouched_anchor(frame, "anchor", {"lookback": 2, "active_bars": 1}, "long")
    assert trace["untouched_prior"][0] is False
    assert trace["untouched_prior"] == _untouched_prior_reference(touch_pattern, 2)


# ---- recent_max parity (via _anchor_stack_width) ----


def test_recent_max_parity_edge_cases() -> None:
    cases = [
        (1.0, 2.0, 3.0, 4.0, 5.0),
        (float("nan"), 1.0, 2.0, float("nan"), 3.0),
        (1.0,) * 10,
        (float("nan"),) * 5,
        (float("inf"), 1.0, 2.0, 3.0, 4.0),
    ]
    for width in cases:
        for lookback in (1, 2, 3, 5):
            n = len(width)
            frame = _plain_frame(
                closes=("10",) * n,
                series={
                    "fast": tuple(
                        str(v) if math.isfinite(v) else ("inf" if v > 0 else "-inf") for v in width
                    ),
                    "anchor": ("0",) * n,
                    "slow": ("0",) * n,
                    "atr": ("1",) * n,
                },
            )
            # Drive width_atr = |fast - slow| / atr = fast / 1 = fast directly by
            # setting anchor/slow=0, atr=1, so width_atr[i] == fast[i] exactly
            # (matching the `width` fixture) for both finite and non-finite values.
            params = {
                "min_current_width_atr": 1e-9,
                "min_recent_width_atr": 1e-9,
                "width_lookback_bars": lookback,
            }
            columns = {"fast": "fast", "anchor": "anchor", "slow": "slow", "atr": "atr"}
            _, trace = _anchor_stack_width(frame, columns, params)
            expected = _recent_max_reference(width, lookback)
            assert _nan_aware_equal(trace["recent_max_width_atr"], expected)


def test_recent_max_full_window_all_finite_vs_gate_false_before_full_window() -> None:
    width = (1.0, 2.0, 3.0, 4.0, 5.0)
    lookback = 3
    n = len(width)
    frame = _plain_frame(
        closes=("10",) * n,
        series={
            "fast": tuple(str(v) for v in width),
            "anchor": ("0",) * n,
            "slow": ("0",) * n,
            "atr": ("1",) * n,
        },
    )
    params = {
        "min_current_width_atr": 1e-9,
        "min_recent_width_atr": 1e-9,
        "width_lookback_bars": lookback,
    }
    columns = {"fast": "fast", "anchor": "anchor", "slow": "slow", "atr": "atr"}
    _, trace = _anchor_stack_width(frame, columns, params)
    recent = trace["recent_max_width_atr"]
    # index < lookback - 1 => no full window yet => NaN
    assert math.isnan(recent[0])
    assert math.isnan(recent[1])
    # index >= lookback - 1 => full all-finite window => real max
    assert recent[2] == 3.0
    assert recent[3] == 4.0
    assert recent[4] == 5.0


def test_recent_max_full_window_containing_nan_is_blocked() -> None:
    width = (1.0, 2.0, float("nan"), 4.0, 5.0)
    lookback = 3
    n = len(width)
    frame = _plain_frame(
        closes=("10",) * n,
        series={
            "fast": tuple("nan" if math.isnan(v) else str(v) for v in width),
            "anchor": ("0",) * n,
            "slow": ("0",) * n,
            "atr": ("1",) * n,
        },
    )
    params = {
        "min_current_width_atr": 1e-9,
        "min_recent_width_atr": 1e-9,
        "width_lookback_bars": lookback,
    }
    columns = {"fast": "fast", "anchor": "anchor", "slow": "slow", "atr": "atr"}
    _, trace = _anchor_stack_width(frame, columns, params)
    recent = trace["recent_max_width_atr"]
    # window [0,1,nan] at index 2 -> gate false -> NaN
    assert math.isnan(recent[2])
    # window [1,nan,4] at index 3 -> still contains the NaN -> gate false -> NaN
    assert math.isnan(recent[3])
    # window [nan,4,5] at index 4 -> still contains the NaN -> gate false -> NaN
    assert math.isnan(recent[4])


def test_recent_max_parity_random() -> None:
    rng = random.Random(5678)
    for _ in range(50):
        n = rng.randint(1, 50)
        # width_atr is always non-negative in production (abs(fast-slow)/atr);
        # the harness below derives it as fast/atr with anchor=slow=0, atr=1,
        # so only non-negative fixture values reproduce that invariant.
        width = tuple(float("nan") if rng.random() < 0.15 else rng.uniform(0, 5) for _ in range(n))
        lookback = rng.randint(1, n + 3)
        frame = _plain_frame(
            closes=("10",) * n,
            series={
                "fast": tuple("nan" if math.isnan(v) else str(v) for v in width),
                "anchor": ("0",) * n,
                "slow": ("0",) * n,
                "atr": ("1",) * n,
            },
        )
        params = {
            "min_current_width_atr": 1e-9,
            "min_recent_width_atr": 1e-9,
            "width_lookback_bars": lookback,
        }
        columns = {"fast": "fast", "anchor": "anchor", "slow": "slow", "atr": "atr"}
        _, trace = _anchor_stack_width(frame, columns, params)
        expected = _recent_max_reference(width, lookback)
        assert _nan_aware_equal(trace["recent_max_width_atr"], expected)


# ---- _combine_setup_masks parity ----


def test_combine_setup_masks_empty_is_all_true() -> None:
    assert _combine_setup_masks((), 5) == (True,) * 5


def test_combine_setup_masks_single_mask() -> None:
    mask = (True, False, True, True, False)
    assert _combine_setup_masks((mask,), 5) == mask


def test_combine_setup_masks_multiple_all_true() -> None:
    masks = ((True,) * 4, (True,) * 4, (True,) * 4)
    assert _combine_setup_masks(masks, 4) == (True,) * 4


def test_combine_setup_masks_multiple_all_false() -> None:
    masks = ((False,) * 4, (True,) * 4)
    assert _combine_setup_masks(masks, 4) == (False,) * 4


def test_combine_setup_masks_mixed() -> None:
    masks = (
        (True, True, False, True),
        (True, False, True, True),
        (True, True, True, False),
    )
    expected = _setups_ok_reference(masks, 4)
    assert _combine_setup_masks(masks, 4) == expected
    assert expected == (True, False, False, False)
