from __future__ import annotations

from decimal import Decimal

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.context_consumption import ContextConsumptionRecord
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    _combine_blocker_masks,
    _rsi_blocker,
    _trend_strength_blocker,
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)


def frame() -> FeatureFrame:
    market = MarketStream("BTCUSDT.P", "5m")
    return FeatureFrame(
        market=market,
        requested_range=TimeRange(0, 1_200_000),
        time_ms=(0, 300_000, 600_000, 900_000),
        series={
            "ema_close_base_2": ("3", "2", "1", "4"),
            "ema_close_base_3": ("2", "2", "2", "3"),
            "ema_close_base_5": ("1", "2", "3", "2"),
            "rsi_close_base_3": ("50", "85", "50", "50"),
        },
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=tuple(
            MarketBar(t, Decimal(o), Decimal("5"), Decimal("0"), Decimal(c), Decimal("1"))
            for t, o, c in zip(
                (0, 300_000, 600_000, 900_000),
                ("1", "2", "3", "4"),
                ("2", "1", "3", "5"),
                strict=True,
            )
        ),
    )


def spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [
                {"instance_id": "candle", "component_id": "counter_candle_blocker"},
                {
                    "instance_id": "rsi",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "rsi": {"timeframe": "base", "period": 3},
                    "lookback": 2,
                    "long_block_above": 80,
                    "short_block_below": 20,
                },
            ],
        },
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


def test_direction_and_multiple_blockers_are_composed_per_side() -> None:
    planned = build_feature_plan_from_canonical_spec(spec())
    output = evaluate_direction_and_blockers(spec(), frame(), planned, ())
    long, short = output
    assert long.direction.allowed == (True, False, False, True)
    assert long.blockers[0].allowed == (True, False, True, True)
    assert long.blockers[1].allowed == (True, False, False, True)
    assert long.blockers_ok == (True, False, False, True)
    assert long.pre_setup_allowed == (True, False, False, True)
    assert short.direction.allowed == (False, False, True, False)


def test_context_gate_is_applied_after_intrinsic_blocker() -> None:
    raw = spec()
    blockers = raw["components"]["blockers"]  # type: ignore[index]
    blockers[0]["context_consumption"] = {  # type: ignore[index]
        "context_ref": "htf",
        "policy": {"policy_id": "htf_regime_gate", "params": {"allowed_regimes": ["aligned"]}},
    }
    planned = build_feature_plan_from_canonical_spec(raw)
    record = ContextConsumptionRecord(
        role="blocker",
        context_ref="htf",
        policy_id="htf_regime_gate",
        side="long",
        component_id="counter_candle_blocker",
        instance_id="candle",
        raw_state=("up", "down", "up", "down"),
        allowed=(True, False, True, False),
        allowed_regimes=("aligned",),
    )
    output = evaluate_direction_and_blockers(raw, frame(), planned, (record,))
    assert output[0].blockers[0].intrinsic_allowed == (True, False, True, True)
    assert output[0].blockers[0].allowed == (True, False, True, False)


# -- _rsi_blocker / _trend_strength_blocker / _combine_blocker_masks:
# direct unit parity for the vectorized replacements (direction-blockers-
# vectorization: exact positional semantics preserved -- see design.md
# Decisions 1-3.)


def _rsi_frame_and_plan(values: tuple[str | None, ...]) -> tuple[FeatureFrame, object, str]:
    raw = spec()
    plan = build_feature_plan_from_canonical_spec(raw)
    output_id = plan.rsi_columns[("base", 3)]
    times = tuple(i * 300_000 for i in range(len(values)))
    frame_obj = FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, times[-1] + 300_000 if times else 300_000),
        time_ms=times,
        series={output_id: values},
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=(),
    )
    return frame_obj, plan, output_id


def _rsi_item(*, lookback: int, long_block_above: float = 80.0, short_block_below: float = 20.0):
    return {
        "rsi": {"timeframe": "base", "period": 3},
        "lookback": lookback,
        "long_block_above": long_block_above,
        "short_block_below": short_block_below,
    }


def test_rsi_blocker_normal_and_warmup_nan() -> None:
    # first two bars are warmup (None -> NaN), never "extreme"
    frame_obj, plan, _ = _rsi_frame_and_plan((None, None, "50", "90", "50", "50"))
    allowed, trace = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "long")
    assert allowed == (True, True, True, False, False, True)
    assert trace["extreme_seen"] == (False, False, False, True, True, False)


def test_rsi_blocker_all_pass() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("50", "50", "50", "50"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "long")
    assert allowed == (True, True, True, True)


def test_rsi_blocker_all_block() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("90", "90", "90", "90"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "long")
    assert allowed == (False, False, False, False)


def test_rsi_blocker_alternating() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("90", "10", "90", "10", "90"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "long")
    assert allowed == (False, False, False, False, False)


def test_rsi_blocker_short_side() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("10", "50", "50", "50"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "short")
    assert allowed == (False, False, True, True)


def test_rsi_blocker_threshold_equality_is_not_extreme() -> None:
    # strict > / < : exactly-at-threshold does not count as extreme
    frame_obj, plan, _ = _rsi_frame_and_plan(("80", "80", "80"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2, long_block_above=80.0), frame_obj, plan, "long")
    assert allowed == (True, True, True)


def test_rsi_blocker_lookback_one() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("90", "50", "90", "50"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=1), frame_obj, plan, "long")
    assert allowed == (False, True, False, True)


def test_rsi_blocker_lookback_larger_than_frame() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("50", "50", "90", "50"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=100), frame_obj, plan, "long")
    assert allowed == (True, True, False, False)


def test_rsi_blocker_all_nan() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan((None, None, None))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "long")
    assert allowed == (True, True, True)


def test_rsi_blocker_infinities_are_not_extreme() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("inf", "-inf", "50"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=2), frame_obj, plan, "long")
    assert allowed == (True, True, True)


def test_rsi_blocker_first_last_bar() -> None:
    frame_obj, plan, _ = _rsi_frame_and_plan(("90", "50", "50", "10"))
    allowed, _ = _rsi_blocker(_rsi_item(lookback=1), frame_obj, plan, "short")
    assert allowed[0] is True  # first bar: 90 not < short_block_below=20
    assert allowed[-1] is False  # last bar: 10 < 20 -> extreme -> blocked


def _trend_frame_and_plan(
    adx: tuple[str | None, ...], plus: tuple[str | None, ...], minus: tuple[str | None, ...]
) -> tuple[FeatureFrame, object, dict[str, str]]:
    raw = spec()
    components = raw["components"]  # type: ignore[index]
    components["blockers"].append(  # type: ignore[index]
        {
            "instance_id": "trend",
            "component_id": "trend_strength_episode_blocker",
            "trend_strength": {"timeframe": "base", "adx_period": 14},
        }
    )
    plan = build_feature_plan_from_canonical_spec(raw)
    columns = plan.adx_dmi_columns[("base", 14)]
    times = tuple(i * 300_000 for i in range(len(adx)))
    frame_obj = FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, times[-1] + 300_000 if times else 300_000),
        time_ms=times,
        series={columns["adx"]: adx, columns["di_plus"]: plus, columns["di_minus"]: minus},
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=(),
    )
    return frame_obj, plan, columns


def _trend_item(**trend_overrides: object):
    trend_strength = {
        "timeframe": "base",
        "adx_period": 14,
        "min_adx_peak": 25.0,
        "peak_lookback_bars": 3,
        "max_bars_since_peak": 2,
        "min_current_adx": 15.0,
        "require_di_alignment_on_peak": True,
        "block_on_opposite_di_flip": True,
        "opposite_di_margin": 0.0,
        **trend_overrides,
    }
    return {"trend_strength": trend_strength}


def test_trend_strength_normal_reference_case() -> None:
    # bar0/bar1: each is itself a qualifying peak (adx=30>=25, aligned) -> allowed.
    # bar2: nearest qualifying peak is bar1 (age=1, within max_since=2), but
    # bar2's own current adx=10 < min_current_adx=15 -> current_adx_too_low.
    adx = ("30", "30", "10")
    plus = ("40", "40", "40")
    minus = ("10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(_trend_item(), frame_obj, plan, "long")
    assert allowed == (True, True, False)
    assert trace["adx_peak_idx"] == (0, 1, 1)
    assert trace["bars_since_adx_peak"] == (0, 0, 1)
    assert trace["blocked_reason"] == ("", "", "current_adx_too_low")


def test_trend_strength_current_indicator_not_ready() -> None:
    adx = (None, "30", "30")
    plus = ("40", "40", "40")
    minus = ("10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(_trend_item(), frame_obj, plan, "long")
    assert allowed[0] is False
    assert trace["blocked_reason"][0] == "indicator_not_ready"
    assert trace["adx_peak_idx"][0] == -1
    assert trace["bars_since_adx_peak"][0] == -1


def test_trend_strength_candidate_nan_inside_lookup_window() -> None:
    # bar0 qualifies (peak). bar1 has NaN adx (not a valid candidate, but current
    # bar1 itself is NOT the finite-gate target here -- di_plus/minus ARE finite
    # for bar1's own values would matter only if bar1 were "current"; here we
    # check that the NaN *candidate* bar1 is skipped when searching backward
    # from bar2, without invalidating bar2's own finite current-bar status.
    adx = ("30", None, "10")
    plus = ("40", "40", "40")
    minus = ("10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=3, max_bars_since_peak=5), frame_obj, plan, "long"
    )
    # bar2 is finite (adx=10) -- searches back through bar1 (NaN, skipped) to bar0 (peak).
    # peak_index/bars_since are recorded regardless of what blocks afterward;
    # bar2 is still blocked because its own current adx=10 < default
    # min_current_adx=15.0 (current_adx_too_low), checked after peak lookup.
    assert trace["adx_peak_idx"][2] == 0
    assert trace["bars_since_adx_peak"][2] == 2
    assert allowed[2] is False
    assert trace["blocked_reason"][2] == "current_adx_too_low"


def test_trend_strength_no_recent_peak() -> None:
    adx = ("10", "10", "10")
    plus = ("40", "40", "40")
    minus = ("10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(_trend_item(), frame_obj, plan, "long")
    assert allowed == (False, False, False)
    assert trace["blocked_reason"] == ("no_recent_adx_peak",) * 3
    assert trace["adx_peak_idx"] == (-1, -1, -1)


def test_trend_strength_peak_too_old() -> None:
    adx = ("30", "10", "10", "10", "10")
    plus = ("40", "40", "40", "40", "40")
    minus = ("10", "10", "10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=5, max_bars_since_peak=2), frame_obj, plan, "long"
    )
    # bar4: peak at bar0 is still within lookback(5) but age(4) > max_since(2)
    assert trace["adx_peak_idx"][4] == 0
    assert trace["blocked_reason"][4] == "peak_too_old"
    assert allowed[4] is False


def test_trend_strength_min_peak_exact_equality_qualifies() -> None:
    adx = ("25.0", "10")
    plus = ("40", "40")
    minus = ("10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(min_adx_peak=25.0), frame_obj, plan, "long"
    )
    assert trace["adx_peak_idx"][0] == 0  # 25.0 >= 25.0 qualifies


def test_trend_strength_min_current_exact_boundary() -> None:
    adx = ("30", "15.0")
    plus = ("40", "40")
    minus = ("10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(min_current_adx=15.0, peak_lookback_bars=2, max_bars_since_peak=5),
        frame_obj,
        plan,
        "long",
    )
    # adx[1]=15.0 is NOT < 15.0 -> current_adx_too_low does not trigger
    assert trace["blocked_reason"][1] != "current_adx_too_low"


def test_trend_strength_require_alignment_true_vs_false() -> None:
    # plus < minus at the candidate -> not aligned for "long"
    adx = ("30", "10")
    plus = ("10", "10")
    minus = ("40", "40")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed_strict, trace_strict = _trend_strength_blocker(
        _trend_item(require_di_alignment_on_peak=True), frame_obj, plan, "long"
    )
    assert trace_strict["adx_peak_idx"][0] == -1  # not aligned -> does not qualify
    allowed_loose, trace_loose = _trend_strength_blocker(
        _trend_item(require_di_alignment_on_peak=False), frame_obj, plan, "long"
    )
    assert trace_loose["adx_peak_idx"][0] == 0  # alignment not required -> qualifies


def test_trend_strength_block_flip_true_vs_false() -> None:
    adx = ("30", "30")
    plus = ("40", "10")
    minus = ("10", "40")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed_block, trace_block = _trend_strength_blocker(
        _trend_item(block_on_opposite_di_flip=True, peak_lookback_bars=2, max_bars_since_peak=5),
        frame_obj,
        plan,
        "long",
    )
    assert trace_block["blocked_reason"][1] == "opposite_di_flip"
    assert allowed_block[1] is False
    allowed_noflip, trace_noflip = _trend_strength_blocker(
        _trend_item(block_on_opposite_di_flip=False, peak_lookback_bars=2, max_bars_since_peak=5),
        frame_obj,
        plan,
        "long",
    )
    assert trace_noflip["blocked_reason"][1] == ""
    assert allowed_noflip[1] is True


def test_trend_strength_di_margin() -> None:
    # di_minus is only slightly above di_plus; a positive margin should
    # tolerate that and not count it as an opposite flip.
    adx = ("30", "30")
    plus = ("40", "39")
    minus = ("10", "40")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    _, trace_no_margin = _trend_strength_blocker(
        _trend_item(opposite_di_margin=0.0, peak_lookback_bars=2, max_bars_since_peak=5),
        frame_obj,
        plan,
        "long",
    )
    assert trace_no_margin["blocked_reason"][1] == "opposite_di_flip"
    _, trace_with_margin = _trend_strength_blocker(
        _trend_item(opposite_di_margin=5.0, peak_lookback_bars=2, max_bars_since_peak=5),
        frame_obj,
        plan,
        "long",
    )
    assert trace_with_margin["blocked_reason"][1] == ""


def test_trend_strength_short_side() -> None:
    adx = ("30", "30")
    plus = ("10", "10")
    minus = ("40", "40")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=2, max_bars_since_peak=5), frame_obj, plan, "short"
    )
    assert trace["adx_peak_idx"][0] == 0
    assert allowed[0] is True


def test_trend_strength_peak_lookback_one() -> None:
    adx = ("30", "10")
    plus = ("40", "40")
    minus = ("10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=1, max_bars_since_peak=5), frame_obj, plan, "long"
    )
    # bar1 can only see itself (lookback=1) -- adx=10 doesn't qualify -> no peak
    assert trace["adx_peak_idx"][1] == -1
    assert trace["blocked_reason"][1] == "no_recent_adx_peak"


def test_trend_strength_first_last_bar() -> None:
    adx = ("30", "10", "10", "30")
    plus = ("40", "40", "40", "40")
    minus = ("10", "10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=4, max_bars_since_peak=10), frame_obj, plan, "long"
    )
    assert trace["adx_peak_idx"][0] == 0
    assert trace["adx_peak_idx"][-1] == 3


def test_trend_strength_max_since_exact_boundary() -> None:
    adx = ("30", "10", "10")
    plus = ("40", "40", "40")
    minus = ("10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=3, max_bars_since_peak=2), frame_obj, plan, "long"
    )
    # bar2: age = 2 - 0 = 2, NOT > max_since=2 -> peak_too_old does not trigger
    assert trace["blocked_reason"][2] != "peak_too_old"


def test_trend_strength_infinities_never_qualify_or_gate_current() -> None:
    adx = ("inf", "30", "-inf")
    plus = ("40", "40", "40")
    minus = ("10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=3, max_bars_since_peak=5), frame_obj, plan, "long"
    )
    assert trace["blocked_reason"][0] == "indicator_not_ready"
    assert trace["blocked_reason"][2] == "indicator_not_ready"
    # bar1 (finite, 30) must not treat bar0's inf as a qualifying peak
    assert trace["adx_peak_idx"][1] == 1


def test_trend_strength_reason_priority_when_multiple_conditions_hold() -> None:
    # Construct a bar where BOTH peak_too_old and current_adx_too_low would
    # apply if checked independently -- peak_too_old must win (checked first).
    adx = ("30", "5", "5", "5")
    plus = ("40", "40", "40", "40")
    minus = ("10", "10", "10", "10")
    frame_obj, plan, _ = _trend_frame_and_plan(adx, plus, minus)
    allowed, trace = _trend_strength_blocker(
        _trend_item(peak_lookback_bars=4, max_bars_since_peak=1, min_current_adx=15.0),
        frame_obj,
        plan,
        "long",
    )
    # bar3: peak at bar0, age=3 > max_since=1 (peak_too_old) AND
    # current adx=5 < 15 (current_adx_too_low) -- peak_too_old has priority.
    assert trace["adx_peak_idx"][3] == 0
    assert trace["blocked_reason"][3] == "peak_too_old"


def test_combine_blocker_masks_empty() -> None:
    assert _combine_blocker_masks((), 5) == (True, True, True, True, True)


def test_combine_blocker_masks_single_blocker() -> None:
    mask = (True, False, True)
    assert _combine_blocker_masks((mask,), 3) == mask


def test_combine_blocker_masks_multiple_all_true() -> None:
    result = _combine_blocker_masks(((True, True), (True, True), (True, True)), 2)
    assert result == (True, True)


def test_combine_blocker_masks_multiple_all_false() -> None:
    result = _combine_blocker_masks(((False, False), (True, True)), 2)
    assert result == (False, False)


def test_combine_blocker_masks_mixed() -> None:
    result = _combine_blocker_masks(
        ((True, True, False), (True, False, False), (False, True, True)), 3
    )
    assert result == (False, False, False)
