"""Unit tests for ResolveIndicatorHistoryRequirements."""

from __future__ import annotations

import math

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.strategies.live_calculation.indicator_requirements import (
    ResolveIndicatorHistoryRequirements,
    _adx_dmi_convergence_bars,
    _ema_convergence_bars,
)

_TOLERANCE = 1e-6


def _plan(*features: PlannedFeature) -> IndicatorPlan:
    return IndicatorPlan(plan_version="v1", features=tuple(features))


def test_rsi_is_finite_window_equal_to_period() -> None:
    plan = _plan(PlannedFeature("rsi_1", "rsi", "base", "close", {"period": 14}))
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    assert reqs[0].bars == 14
    assert reqs[0].timeframe == "base"


def test_atr_is_finite_window_equal_to_period() -> None:
    plan = _plan(PlannedFeature("atr_1", "atr", "base", "close", {"period": 14}))
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    assert reqs[0].bars == 14


def test_ema_uses_one_minus_alpha_decay_not_alpha() -> None:
    period = 200
    alpha = 2.0 / (period + 1)
    # Hand-computed expected: smallest n with (1-alpha)^n < tolerance.
    expected = math.ceil(math.log(_TOLERANCE) / math.log(1 - alpha))
    plan = _plan(PlannedFeature("ema_1", "ema", "base", "close", {"period": period}))
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    assert reqs[0].bars == expected
    # Sanity: correct decay base gives hundreds/thousands of bars for EMA200,
    # not a handful -- guards against the alpha^n regression.
    assert reqs[0].bars > 1000


def test_ema_convergence_bars_matches_direct_formula() -> None:
    assert _ema_convergence_bars(200, 1e-6) == math.ceil(
        math.log(1e-6) / math.log(1 - 2.0 / 201)
    )


def test_adx_dmi_is_recursive_not_finite_and_independent_of_ema_policy() -> None:
    period = 14
    plan = _plan(PlannedFeature("adx_1", "adx", "base", "close", {"period": period}))
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    # Hand-computed independently of _wilder_convergence_bars/
    # _adx_dmi_convergence_bars: Wilder's decay base is (period-1)/period,
    # and the provisional policy is 2*period + 2*single_stage (see
    # test_adx_dmi_structural_term_is_at_least_two_bootstrap_windows for why
    # it is "provisional", not a precisely derived bound).
    decay_base = (period - 1) / period
    single_stage = math.ceil(math.log(_TOLERANCE) / math.log(decay_base))
    expected = 2 * period + 2 * single_stage
    assert reqs[0].bars == expected
    # Must not equal the EMA-policy bar count for the same period/tolerance.
    assert reqs[0].bars != _ema_convergence_bars(period, _TOLERANCE)


def test_adx_dmi_structural_term_is_at_least_two_bootstrap_windows() -> None:
    """compute_adx_dmi's second wilder_rma pass (DX -> ADX) needs its own
    `period` consecutive finite DX inputs -- two independent Wilder
    bootstraps, not one -- so the structural (non-convergence) component of
    the requirement must scale with `period`, not be a small constant.

    This isolates the structural term from the convergence term by using
    tolerance=1.0, where `_wilder_convergence_bars` floors to 1 (its `max(1,
    ...)` clamp) and contributes no more than +2 -- so what's left is almost
    entirely the structural bootstrap-window count. A one-bootstrap formula
    (e.g. the previously-shipped `period + 2 * single_stage`) would return
    roughly `period + 2` here, well under `1.5 * period` for any period > 4;
    a two-bootstrap formula returns roughly `2 * period + 2`. This is the
    check the previous `>= 2 * period` bound did NOT provide: at a realistic
    convergence tolerance the single_stage term dominates and swamps the
    structural term, so that check passed even against the one-bootstrap
    formula and would not have caught the original bug."""

    period = 20
    trivial_tolerance = 1.0
    structural_dominated_bars = _adx_dmi_convergence_bars(period, trivial_tolerance)
    assert structural_dominated_bars >= 1.5 * period


@pytest.mark.parametrize("kind", ["di_plus", "di_minus"])
def test_di_plus_minus_use_same_wilder_cascade_as_adx(kind: str) -> None:
    plan = _plan(PlannedFeature("dmi_1", kind, "base", "close", {"period": 14}))
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    assert reqs[0].bars == _adx_dmi_convergence_bars(14, _TOLERANCE)


def test_atr_distance_contributes_zero_additional_warmup() -> None:
    plan = _plan(
        PlannedFeature("atr_1", "atr", "base", "close", {"period": 14}),
        PlannedFeature(
            "atr_distance_1",
            "atr_distance",
            "base",
            None,
            {"multiplier": 1.5},
            dependencies=("atr_1",),
        ),
    )
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    by_id = {f.output_id: r for f, r in zip(plan.features, reqs, strict=True)}
    assert by_id["atr_distance_1"].bars == 0
    assert by_id["atr_1"].bars == 14


def test_unrecognized_indicator_kind_fails_closed() -> None:
    plan = _plan(PlannedFeature("mystery_1", "some_future_indicator", "base", "close", {}))
    with pytest.raises(InvalidRequestError):
        ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)


def test_higher_timeframe_requirement_keeps_its_own_timeframe_label() -> None:
    plan = _plan(PlannedFeature("ema_4h", "ema", "4h", "close", {"period": 200}))
    reqs = ResolveIndicatorHistoryRequirements(
        ema_tolerance=_TOLERANCE, adx_dmi_tolerance=_TOLERANCE
    ).execute(plan)
    assert reqs[0].timeframe == "4h"
