"""Resolve per-indicator live history requirements from an existing IndicatorPlan.

Pure computation only: reads PlannedFeature entries and returns HistoryRequirement
values. No MDS, no pandas, no HTTP.
"""

from __future__ import annotations

import math

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.strategies.live_calculation.contracts import HistoryRequirement

# Convergence tolerances for recursively-computed indicators, calibrated
# against real BTCUSDT.P/ETHUSDT.P 5m history under a numeric-parity
# comparison (every IndicatorPlan output plus every downstream numeric/trace
# value, not just categorical outcomes -- design.md). Kept as two separate
# constants: EMA and the Wilder RMA cascade used by ADX/DI are independent
# recursive processes with independently calibrated tolerances. See
# openspec/changes/bounded-live-calculation-window design.md for the
# empirical basis.
_CALIBRATED_EMA_CONVERGENCE_TOLERANCE = 1e-4
_CALIBRATED_ADX_DMI_CONVERGENCE_TOLERANCE = 1e-4

_FINITE_KINDS = {"rsi", "atr"}
_EMA_KINDS = {"ema"}
_WILDER_KINDS = {"adx", "di_plus", "di_minus"}
_ZERO_WARMUP_KINDS = {"atr_distance"}


def _ema_convergence_bars(period: int, tolerance: float) -> int:
    """Bars n such that (1 - alpha)^n < tolerance, alpha = 2 / (period + 1).

    NOT alpha^n -- see design.md Decision 7 for why the decay base is
    (1 - alpha), matching pandas' .ewm(span=period, adjust=False).
    """

    alpha = 2.0 / (period + 1)
    decay_base = 1.0 - alpha
    if decay_base <= 0.0:
        return 1
    return max(1, math.ceil(math.log(tolerance) / math.log(decay_base)))


def _wilder_convergence_bars(period: int, tolerance: float) -> int:
    """Bars for one Wilder RMA smoothing pass to converge below tolerance.

    Wilder's recursive update is out[i] = (previous * (period - 1) + current) / period,
    a decay base of (period - 1) / period -- distinct from the EMA formula above,
    per design.md Decision 7.
    """

    if period <= 1:
        return 1
    decay_base = (period - 1) / period
    return max(1, math.ceil(math.log(tolerance) / math.log(decay_base)))


def _adx_dmi_convergence_bars(period: int, tolerance: float) -> int:
    """compute_adx_dmi is a two-stage recursive cascade -- wilder_rma smooths
    TR/+DM/-DM first, then a *second*, independent wilder_rma pass smooths
    DX into ADX -- so it needs two bootstrap windows, not one.

    IMPORTANT (corrected after review -- do not reintroduce the earlier
    mistake): dx and adx are both computed (lines `dx = ...` / `adx =
    wilder_rma(dx, ...)`) *before* compute_adx_dmi's `di_plus.iloc[:period] =
    np.nan` / `di_minus.iloc[:period] = np.nan` masking runs. That masking
    only affects the *returned* DI+/DI- series -- it has no effect on dx or
    adx, which are already computed from the unmasked values. So it is WRONG
    to reason "DI+/DI- are NaN through index period, therefore DX is only
    valid from index period" -- that gets the execution order backwards. dx
    is actually valid as soon as smooth_plus/smooth_minus/smooth_tr are
    (wilder_rma's own bootstrap, index period - 1), assuming di_sum is
    nonzero. The second wilder_rma(dx, period) pass then needs its own
    `period` consecutive finite dx values starting there, i.e. bootstraps at
    index (period - 1) + (period - 1) = 2*period - 2 -- so ADX has no valid
    value before index 2*period - 2 (2*period - 1 bars), not the previously
    claimed 2*period.

    This function still returns 2 * period + 2 * single_stage (not 2*period -
    1 + ...): that is a deliberately round, over-provisioned placeholder, not
    a claim of a precisely derived convergence bound -- a provisional
    conservative policy, not a proven-exact correctness fix. Compounding seed
    influence between the two stages is also not modeled precisely here.
    """

    single_stage = _wilder_convergence_bars(period, tolerance)
    return 2 * period + 2 * single_stage


class ResolveIndicatorHistoryRequirements:
    """Derive one HistoryRequirement per planned indicator feature."""

    def __init__(
        self,
        *,
        ema_tolerance: float = _CALIBRATED_EMA_CONVERGENCE_TOLERANCE,
        adx_dmi_tolerance: float = _CALIBRATED_ADX_DMI_CONVERGENCE_TOLERANCE,
    ) -> None:
        self._ema_tolerance = ema_tolerance
        self._adx_dmi_tolerance = adx_dmi_tolerance

    def execute(self, plan: IndicatorPlan) -> tuple[HistoryRequirement, ...]:
        requirements: list[HistoryRequirement] = []
        for feature in plan.features:
            requirements.append(self._resolve_one(feature))
        return tuple(requirements)

    def _resolve_one(self, feature: PlannedFeature) -> HistoryRequirement:
        kind = feature.kind
        if kind in _ZERO_WARMUP_KINDS:
            return HistoryRequirement(
                timeframe=feature.timeframe,
                bars=0,
                reason=f"{feature.output_id}: {kind} inherits upstream dependency's own "
                "requirement, contributes zero additional warm-up",
            )
        if kind in _FINITE_KINDS:
            period = int(feature.parameters["period"])
            return HistoryRequirement(
                timeframe=feature.timeframe,
                bars=period,
                reason=f"{feature.output_id}: finite {kind}(period={period}) rolling window",
            )
        if kind in _EMA_KINDS:
            period = int(feature.parameters["period"])
            bars = _ema_convergence_bars(period, self._ema_tolerance)
            return HistoryRequirement(
                timeframe=feature.timeframe,
                bars=bars,
                reason=(
                    f"{feature.output_id}: ema(period={period}) convergence warm-up "
                    f"at tolerance={self._ema_tolerance}"
                ),
            )
        if kind in _WILDER_KINDS:
            period = int(feature.parameters["period"])
            bars = _adx_dmi_convergence_bars(period, self._adx_dmi_tolerance)
            return HistoryRequirement(
                timeframe=feature.timeframe,
                bars=bars,
                reason=(
                    f"{feature.output_id}: {kind}(period={period}) Wilder RMA cascade "
                    f"convergence warm-up at tolerance={self._adx_dmi_tolerance}"
                ),
            )
        raise InvalidRequestError(
            "no registered live history policy for indicator kind",
            kind=kind,
            output_id=feature.output_id,
        )
