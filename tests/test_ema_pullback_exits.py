from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.exits import (
    _select,
    _select_bool,
    evaluate_exit_policy,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.potential_entries import (
    project_potential_entries,
)
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation
from strategy_engine.strategies.ema_pullback.triggers import (
    SideTriggerEvaluation,
    TriggerMask,
)


def raw_spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "sl",
                            "component_id": "atr_stop_loss",
                            "exit_kind": "stop_loss",
                            "distance": {"timeframe": "base", "period": 2, "multiplier": 1.5},
                        },
                        {
                            "instance_id": "tp",
                            "component_id": "constant_usd_take_profit",
                            "exit_kind": "take_profit",
                            "usd_distance": 4.0,
                        },
                        {
                            "instance_id": "rsi",
                            "component_id": "rsi_signal_exit",
                            "exit_kind": "signal",
                            "rsi": {"timeframe": "base", "period": 2},
                            "long_exit_above": 70.0,
                            "short_exit_below": 30.0,
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


def frame(spec: dict[str, object]) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(spec)
    times = tuple(i * 300_000 for i in range(4))
    bars = tuple(
        MarketBar(
            times[i],
            Decimal(str(100 + i)),
            Decimal(str(102 + i)),
            Decimal(str(99 + i)),
            Decimal(str(100 + i)),
            Decimal("1"),
        )
        for i in range(4)
    )
    series: dict[str, tuple[str | None, ...]] = {
        plan.anchor_columns["fast"]: ("101", "102", "103", "104"),
        plan.anchor_columns["anchor"]: ("100", "101", "102", "103"),
        plan.anchor_columns["slow"]: ("99", "100", "101", "102"),
        plan.rsi_columns[("base", 2)]: (None, "20", "80", "50"),
    }
    if "sl" in plan.exit_distance_columns:
        series[plan.exit_distance_columns["sl"]] = (None, "1.5", "3", "4.5")
    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, 1_200_000),
            times,
            series,
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


def test_exit_policy_returns_signal_and_distance_outputs() -> None:
    spec = raw_spec()
    feature_frame, plan = frame(spec)
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    assert result.signal_exit_long == (False, False, True, False)
    assert result.signal_exit_short == (False, True, False, False)
    assert result.stop_loss_ratio_long[0] is None
    assert result.stop_loss_ratio_long[1] == pytest.approx(1.5 / 101)
    assert result.take_profit_ratio_long[0] == pytest.approx(4 / 100)
    assert result.stop_loss_distance_long == (None, 1.5, 3.0, 4.5)
    assert result.stop_loss_distance_short == (None, 1.5, 3.0, 4.5)
    assert result.take_profit_distance_long == (4.0, 4.0, 4.0, 4.0)
    assert result.take_profit_distance_short == (4.0, 4.0, 4.0, 4.0)
    assert result.stop_ready_long == (False, True, True, True)


def test_raw_distances_do_not_change_exit_policy_wire_output() -> None:
    spec = raw_spec()
    feature_frame, plan = frame(spec)
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    wire = result.to_wire()

    assert set(wire) == {
        "context_state",
        "profile_long",
        "profile_short",
        "signal_exit",
        "stop_loss_ratio",
        "take_profit_ratio",
        "stop_ready",
        "by_profile",
        "rules",
    }
    assert wire["stop_loss_ratio"] == {
        "long": [
            None,
            "0.01485148514851485",
            "0.029411764705882353",
            "0.043689320388349516",
        ],
        "short": [
            None,
            "0.01485148514851485",
            "0.029411764705882353",
            "0.043689320388349516",
        ],
    }
    assert wire["take_profit_ratio"] == {
        "long": ["0.04", "0.039603960396039604", "0.0392156862745098", "0.038834951456310676"],
        "short": ["0.04", "0.039603960396039604", "0.0392156862745098", "0.038834951456310676"],
    }


def test_atr_raw_distance_is_applied_to_anchor_when_close_differs() -> None:
    spec = raw_spec()
    feature_frame, plan = frame(spec)
    series = dict(feature_frame.series)
    series[plan.anchor_columns["anchor"]] = ("90", "91", "92", "93")
    feature_frame = replace(feature_frame, series=series)
    exits = evaluate_exit_policy(spec, feature_frame, plan, ())
    allowed = (True,) * len(feature_frame.time_ms)
    setups = (SideSetupEvaluation("long", (), allowed, allowed),)

    triggers = (
        SideTriggerEvaluation(
            "long",
            TriggerMask(
                "touch_anchor",
                "long",
                allowed,
                {"close_ok": allowed},
            ),
            allowed,
        ),
    )
    projected = project_potential_entries(
        feature_frame, plan, setups, triggers, exits
    )["long"]

    assert projected.stop_price[1] == pytest.approx(91.0 - 1.5)
    assert projected.stop_price[1] != pytest.approx(
        91.0 * (1.0 - exits.stop_loss_ratio_long[1])  # type: ignore[operator]
    )
    assert projected.take_price[1] == pytest.approx(91.0 + 4.0)


def test_unknown_exit_component_is_rejected() -> None:
    spec = raw_spec()
    policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    policy["always_on"]["exits"][0]["component_id"] = "future_exit"  # type: ignore[index]
    feature_frame, plan = frame(spec)
    with pytest.raises(InvalidRequestError, match="unsupported exit component"):
        evaluate_exit_policy(spec, feature_frame, plan, ())


def test_profile_selection_uses_side_relative_context_result() -> None:
    from strategy_engine.strategies.ema_pullback.context_consumption import (
        ContextConsumptionRecord,
    )

    spec = raw_spec()
    policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    policy["always_on"]["exits"] = []  # type: ignore[index]
    policy["profiles"]["aligned"]["exits"] = [  # type: ignore[index]
        {
            "instance_id": "aligned-rsi",
            "component_id": "rsi_signal_exit",
            "exit_kind": "signal",
            "rsi": {"timeframe": "base", "period": 2},
            "long_exit_above": 70.0,
            "short_exit_below": 30.0,
        }
    ]
    feature_frame, plan = frame(spec)
    consumption = (
        ContextConsumptionRecord(
            role="exit_policy",
            context_ref="htf",
            policy_id="exit_profile_by_htf_state",
            side=None,
            component_id="exit_policy",
            instance_id=None,
            raw_state=("up", "down", "up", "down"),
            profile_long=("aligned", "countertrend", "aligned", "countertrend"),
            profile_short=("countertrend", "aligned", "countertrend", "aligned"),
        ),
    )
    result = evaluate_exit_policy(spec, feature_frame, plan, consumption)
    assert result.signal_exit_long == (False, False, True, False)
    assert result.signal_exit_short == (False, True, False, False)


def test_profile_distance_selection_preserves_the_same_minimum_raw_distance() -> None:
    from strategy_engine.strategies.ema_pullback.context_consumption import (
        ContextConsumptionRecord,
    )

    spec = raw_spec()
    policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    policy["always_on"]["exits"].append(  # type: ignore[index]
        {
            "instance_id": "always-sl-2",
            "component_id": "constant_usd_stop_loss",
            "exit_kind": "stop_loss",
            "usd_distance": 2.0,
        }
    )
    policy["profiles"]["aligned"]["exits"] = [  # type: ignore[index]
        {
            "instance_id": "aligned-sl",
            "component_id": "constant_usd_stop_loss",
            "exit_kind": "stop_loss",
            "usd_distance": 1.0,
        }
    ]
    feature_frame, plan = frame(spec)
    consumption = (
        ContextConsumptionRecord(
            role="exit_policy",
            context_ref="htf",
            policy_id="exit_profile_by_htf_state",
            side=None,
            component_id="exit_policy",
            instance_id=None,
            raw_state=("up", "down", "up", "down"),
            profile_long=("aligned", "neutral", "aligned", "neutral"),
            profile_short=("neutral", "aligned", "neutral", "aligned"),
        ),
    )

    result = evaluate_exit_policy(spec, feature_frame, plan, consumption)

    assert result.stop_loss_distance_long == (1.0, 1.5, 1.0, 2.0)
    assert result.stop_loss_distance_short == (2.0, 1.0, 2.0, 1.0)
    for index, raw_distance in enumerate(result.stop_loss_distance_long):
        if raw_distance is not None:
            assert result.stop_loss_ratio_long[index] == pytest.approx(
                raw_distance / float(feature_frame.market_bars[index].close)
            )


def _protection_spec(exits: list[dict[str, object]]) -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": exits},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def _protection_frame(
    spec: dict[str, object], distances: dict[str, tuple[str | None, ...]]
) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(spec)
    times = tuple(i * 300_000 for i in range(4))
    bars = tuple(
        MarketBar(
            times[i],
            Decimal(str(100 + i)),
            Decimal(str(102 + i)),
            Decimal(str(99 + i)),
            Decimal(str(100 + i)),
            Decimal("1"),
        )
        for i in range(4)
    )
    series: dict[str, tuple[str | None, ...]] = {
        plan.anchor_columns["fast"]: ("101", "102", "103", "104"),
        plan.anchor_columns["anchor"]: ("100", "101", "102", "103"),
        plan.anchor_columns["slow"]: ("99", "100", "101", "102"),
    }
    for instance_id, values in distances.items():
        series[plan.exit_distance_columns[instance_id]] = values
    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, 1_200_000),
            times,
            series,
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


def test_configured_stop_series_entirely_null_is_not_ready() -> None:
    spec = _protection_spec(
        [
            {
                "instance_id": "sl",
                "component_id": "atr_stop_loss",
                "exit_kind": "stop_loss",
                "distance": {"timeframe": "base", "period": 2, "multiplier": 1.5},
            }
        ]
    )
    feature_frame, plan = _protection_frame(spec, {"sl": (None, None, None, None)})
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    assert result.stop_ready_long == (False, False, False, False)
    assert result.stop_ready_short == (False, False, False, False)


def test_configured_take_series_entirely_null_is_not_ready() -> None:
    spec = _protection_spec(
        [
            {
                "instance_id": "tp",
                "component_id": "atr_take_profit",
                "exit_kind": "take_profit",
                "distance": {"timeframe": "base", "period": 2, "multiplier": 1.0},
            }
        ]
    )
    feature_frame, plan = _protection_frame(spec, {"tp": (None, None, None, None)})
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    assert result.stop_ready_long == (False, False, False, False)
    assert result.stop_ready_short == (False, False, False, False)


def test_absent_protection_kind_does_not_block_readiness() -> None:
    spec = _protection_spec(
        [
            {
                "instance_id": "sl",
                "component_id": "constant_usd_stop_loss",
                "exit_kind": "stop_loss",
                "usd_distance": 1.0,
            }
        ]
    )
    feature_frame, plan = _protection_frame(spec, {})
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    assert result.stop_ready_long == (True, True, True, True)
    assert result.stop_ready_short == (True, True, True, True)


def test_partially_valid_configured_series_preserves_per_bar_readiness() -> None:
    spec = raw_spec()
    feature_frame, plan = frame(spec)
    result = evaluate_exit_policy(spec, feature_frame, plan, ())
    assert result.stop_ready_long == (False, True, True, True)
    assert result.stop_ready_short == (False, True, True, True)


# -- _select / _select_bool: direct unit parity for the vectorized selector --
# (exit-policy-profile-select-vectorization: positional, not label-aligned,
# fail-closed on unrecognized profile names -- see design.md Decision 1.)

_PROFILE_NAMES = ("aligned", "countertrend", "neutral")


def _float_values(non_default_index: bool = False) -> dict[str, pd.Series]:
    index = pd.Index([10, 20, 30, 40, 50]) if non_default_index else pd.RangeIndex(5)
    return {
        "aligned": pd.Series([1.0, float("nan"), 3.0, 4.0, 5.0], index=index, dtype=float),
        "countertrend": pd.Series(
            [float("nan"), 20.0, float("nan"), 40.0, 50.0], index=index, dtype=float
        ),
        "neutral": pd.Series([100.0, 200.0, 300.0, float("nan"), 500.0], index=index, dtype=float),
    }


def _bool_values(non_default_index: bool = False) -> dict[str, pd.Series]:
    index = pd.Index([10, 20, 30, 40, 50]) if non_default_index else pd.RangeIndex(5)
    return {
        "aligned": pd.Series([True, False, True, False, True], index=index, dtype=bool),
        "countertrend": pd.Series([False, True, False, True, False], index=index, dtype=bool),
        "neutral": pd.Series([False, False, False, False, False], index=index, dtype=bool),
    }


def test_select_all_neutral_profile() -> None:
    values = _float_values()
    profile = ("neutral",) * 5
    result = _select(profile, values, values["neutral"].index)
    expected = values["neutral"].to_numpy()
    assert np.array_equal(result.to_numpy(), expected, equal_nan=True)


def test_select_mixed_profile() -> None:
    values = _float_values()
    profile = ("aligned", "countertrend", "neutral", "aligned", "countertrend")
    result = _select(profile, values, values["aligned"].index)
    expected = np.array([1.0, 20.0, 300.0, 4.0, 50.0])
    assert np.array_equal(result.to_numpy(), expected, equal_nan=True)


def test_select_switches_every_bar() -> None:
    values = _float_values()
    profile = tuple(_PROFILE_NAMES[i % 3] for i in range(5))
    result = _select(profile, values, values["aligned"].index)
    expected = np.array(
        [values[_PROFILE_NAMES[i % 3]].iloc[i] for i in range(5)]
    )
    assert np.array_equal(result.to_numpy(), expected, equal_nan=True)


def test_select_nan_present_in_all_three_profile_series() -> None:
    """Every profile series has a NaN at a different position; selection
    must only reflect the *selected* profile's value at each position."""
    values = _float_values()
    assert math.isnan(values["aligned"].iloc[1])
    assert math.isnan(values["countertrend"].iloc[0])
    assert math.isnan(values["countertrend"].iloc[2])
    assert math.isnan(values["neutral"].iloc[3])
    profile = ("aligned", "aligned", "aligned", "aligned", "aligned")
    result = _select(profile, values, values["aligned"].index)
    # position 1 is NaN in the selected (aligned) series -> NaN in output,
    # even though countertrend/neutral are also NaN elsewhere.
    assert math.isnan(result.iloc[1])
    assert result.iloc[0] == 1.0
    assert result.iloc[2] == 3.0
    assert result.iloc[3] == 4.0
    assert result.iloc[4] == 5.0


def test_select_nan_selected_vs_unselected_positional_behavior() -> None:
    """At a position where the *selected* profile is NaN, output is NaN.
    At a position where the *selected* profile is not NaN but an
    *unselected* profile is NaN at that same position, output is not NaN."""
    values = _float_values()
    # position 0: countertrend is NaN, but we select aligned (=1.0, not NaN)
    profile_select_aligned = ("aligned",) + ("neutral",) * 4
    result_a = _select(profile_select_aligned, values, values["aligned"].index)
    assert result_a.iloc[0] == 1.0  # selected series (aligned) not NaN here
    assert not math.isnan(result_a.iloc[0])

    # position 0: now select countertrend, which IS NaN there
    profile_select_countertrend = ("countertrend",) + ("neutral",) * 4
    result_b = _select(profile_select_countertrend, values, values["aligned"].index)
    assert math.isnan(result_b.iloc[0])


def test_select_bool_selection() -> None:
    values = _bool_values()
    for profile, expected in (
        (("neutral",) * 5, [False, False, False, False, False]),
        (
            ("aligned", "countertrend", "neutral", "aligned", "countertrend"),
            [True, True, False, False, False],
        ),
        (tuple(_PROFILE_NAMES[i % 3] for i in range(5)), None),
    ):
        result = _select_bool(profile, values, values["aligned"].index)
        assert result.dtype == np.dtype(bool)
        if expected is not None:
            assert list(result) == expected
        else:
            assert list(result) == [
                bool(values[profile[i]].iloc[i]) for i in range(5)
            ]


def test_select_preserves_exact_index_including_non_default() -> None:
    values = _float_values(non_default_index=True)
    profile = ("aligned", "countertrend", "neutral", "aligned", "countertrend")
    result = _select(profile, values, values["aligned"].index)
    assert result.index.equals(values["aligned"].index)

    bool_values = _bool_values(non_default_index=True)
    bool_result = _select_bool(profile, bool_values, bool_values["aligned"].index)
    assert bool_result.index.equals(bool_values["aligned"].index)


def test_select_preserves_exact_dtype() -> None:
    values = _float_values()
    profile = ("aligned", "countertrend", "neutral", "aligned", "countertrend")
    float_result = _select(profile, values, values["aligned"].index)
    assert float_result.dtype == np.dtype(np.float64)

    bool_values = _bool_values()
    bool_result = _select_bool(profile, bool_values, bool_values["aligned"].index)
    assert bool_result.dtype == np.dtype(bool)


def test_select_unknown_profile_name_raises_key_error() -> None:
    values = _float_values()
    profile = ("aligned", "totally_unknown_profile", "neutral", "aligned", "countertrend")
    with pytest.raises(KeyError):
        _select(profile, values, values["aligned"].index)


def test_select_bool_unknown_profile_name_raises_key_error() -> None:
    values = _bool_values()
    profile = ("aligned", "totally_unknown_profile", "neutral", "aligned", "countertrend")
    with pytest.raises(KeyError):
        _select_bool(profile, values, values["aligned"].index)
