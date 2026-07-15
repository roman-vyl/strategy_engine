"""Trend strength episode blocker (ADX/DMI memory gate)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from research.strategies.ema_pullback.spec import BlockerRuleSpec
from research.strategies.ema_pullback.spec import TradeSide
from research.strategies.ema_pullback.spec import TrendStrengthEpisodeBlockerParams

BLOCKED_REASON_ALLOW = ""
REASON_INDICATOR_NOT_READY = "indicator_not_ready"
REASON_NO_RECENT_PEAK = "no_recent_adx_peak"
REASON_PEAK_TOO_OLD = "peak_too_old"
REASON_CURRENT_ADX_TOO_LOW = "current_adx_too_low"
REASON_OPPOSITE_DI_FLIP = "opposite_di_flip"

ALL_BLOCKED_REASONS = (
    REASON_INDICATOR_NOT_READY,
    REASON_NO_RECENT_PEAK,
    REASON_PEAK_TOO_OLD,
    REASON_CURRENT_ADX_TOO_LOW,
    REASON_OPPOSITE_DI_FLIP,
)


def _params(rule: BlockerRuleSpec) -> TrendStrengthEpisodeBlockerParams:
    if rule.trend_strength is None:
        raise ValueError("trend_strength_episode_blocker requires trend_strength params")
    return rule.trend_strength


def _di_aligned(side: TradeSide, di_plus: float, di_minus: float) -> bool:
    if side == "long":
        return di_plus > di_minus
    if side == "short":
        return di_minus > di_plus
    raise ValueError("side must be 'long' or 'short'")


def _opposite_di_flip(
    side: TradeSide,
    di_plus: float,
    di_minus: float,
    margin: float,
) -> bool:
    if side == "long":
        return di_minus > di_plus + margin
    return di_plus > di_minus + margin


def _qualifies_peak(
    side: TradeSide,
    adx: float,
    di_plus: float,
    di_minus: float,
    params: TrendStrengthEpisodeBlockerParams,
) -> bool:
    if not np.isfinite(adx) or not np.isfinite(di_plus) or not np.isfinite(di_minus):
        return False
    if adx < params.min_adx_peak:
        return False
    if params.require_di_alignment_on_peak and not _di_aligned(side, di_plus, di_minus):
        return False
    return True


def trend_strength_episode_blocker_trace(
    df: pd.DataFrame,
    side: TradeSide = "long",
    *,
    rule: BlockerRuleSpec,
    adx_col: str,
    di_plus_col: str,
    di_minus_col: str,
) -> dict[str, pd.Series]:
    params = _params(rule)
    adx = df[adx_col].astype(float).to_numpy()
    di_plus = df[di_plus_col].astype(float).to_numpy()
    di_minus = df[di_minus_col].astype(float).to_numpy()

    n = len(df)
    allowed = np.zeros(n, dtype=bool)
    trend_active = np.zeros(n, dtype=bool)
    blocked_reason = np.empty(n, dtype=object)
    adx_peak = np.full(n, np.nan)
    adx_peak_idx = np.full(n, -1, dtype=int)
    bars_since_peak = np.full(n, -1, dtype=int)
    di_plus_at_peak = np.full(n, np.nan)
    di_minus_at_peak = np.full(n, np.nan)
    di_alignment_at_peak = np.zeros(n, dtype=bool)
    opposite_flip = np.zeros(n, dtype=bool)

    lookback = params.peak_lookback_bars

    for t in range(n):
        if (
            not np.isfinite(adx[t])
            or not np.isfinite(di_plus[t])
            or not np.isfinite(di_minus[t])
        ):
            blocked_reason[t] = REASON_INDICATOR_NOT_READY
            continue

        start = max(0, t - lookback + 1)
        peak_idx = -1
        for j in range(t, start - 1, -1):
            if _qualifies_peak(side, adx[j], di_plus[j], di_minus[j], params):
                peak_idx = j
                break

        adx_peak_idx[t] = peak_idx
        if peak_idx >= 0:
            adx_peak[t] = adx[peak_idx]
            di_plus_at_peak[t] = di_plus[peak_idx]
            di_minus_at_peak[t] = di_minus[peak_idx]
            di_alignment_at_peak[t] = _di_aligned(
                side, di_plus[peak_idx], di_minus[peak_idx]
            )
            bars_since_peak[t] = t - peak_idx

        if peak_idx < 0:
            blocked_reason[t] = REASON_NO_RECENT_PEAK
            continue

        if (t - peak_idx) > params.max_bars_since_peak:
            blocked_reason[t] = REASON_PEAK_TOO_OLD
            continue

        if adx[t] < params.min_current_adx:
            blocked_reason[t] = REASON_CURRENT_ADX_TOO_LOW
            continue

        if params.block_on_opposite_di_flip and _opposite_di_flip(
            side, di_plus[t], di_minus[t], params.opposite_di_margin
        ):
            opposite_flip[t] = True
            blocked_reason[t] = REASON_OPPOSITE_DI_FLIP
            continue

        allowed[t] = True
        trend_active[t] = True
        blocked_reason[t] = BLOCKED_REASON_ALLOW

    index = df.index
    return {
        "allowed": pd.Series(allowed, index=index, dtype=bool),
        "trend_strength_active": pd.Series(trend_active, index=index, dtype=bool),
        "blocked_reason": pd.Series(blocked_reason, index=index, dtype=object),
        "adx_current": pd.Series(adx, index=index, dtype=float),
        "adx_peak": pd.Series(adx_peak, index=index, dtype=float),
        "adx_peak_idx": pd.Series(adx_peak_idx, index=index, dtype=int),
        "bars_since_adx_peak": pd.Series(bars_since_peak, index=index, dtype=int),
        "di_plus_current": pd.Series(di_plus, index=index, dtype=float),
        "di_minus_current": pd.Series(di_minus, index=index, dtype=float),
        "di_plus_at_peak": pd.Series(di_plus_at_peak, index=index, dtype=float),
        "di_minus_at_peak": pd.Series(di_minus_at_peak, index=index, dtype=float),
        "di_alignment_at_peak": pd.Series(di_alignment_at_peak, index=index, dtype=bool),
        "opposite_di_flip": pd.Series(opposite_flip, index=index, dtype=bool),
    }


def trend_strength_episode_blocker(
    df: pd.DataFrame,
    side: TradeSide = "long",
    *,
    rule: BlockerRuleSpec,
    adx_col: str,
    di_plus_col: str,
    di_minus_col: str,
) -> pd.Series:
    return trend_strength_episode_blocker_trace(
        df,
        side=side,
        rule=rule,
        adx_col=adx_col,
        di_plus_col=di_plus_col,
        di_minus_col=di_minus_col,
    )["allowed"]


def _blocked_reason_breakdown(trace: dict[str, pd.Series]) -> dict[str, int]:
    allowed = trace["allowed"].fillna(False).astype(bool)
    blocked_reason = trace["blocked_reason"].astype(str)
    breakdown: Counter[str] = Counter()
    for reason, is_blocked in zip(blocked_reason, ~allowed, strict=True):
        if not is_blocked:
            continue
        key = reason if reason else REASON_INDICATOR_NOT_READY
        breakdown[key] += 1
    return dict(sorted(breakdown.items()))


def build_trend_strength_blocker_counters(
    trace: dict[str, pd.Series],
    *,
    final_allowed: pd.Series | None = None,
) -> dict[str, Any]:
    intrinsic = trace["allowed"].fillna(False).astype(bool)
    intrinsic_breakdown = _blocked_reason_breakdown(trace)
    counters: dict[str, Any] = {
        "intrinsic_allowed_count": int(intrinsic.sum()),
        "intrinsic_blocked_count": int((~intrinsic).sum()),
        "intrinsic_blocked_reason_breakdown": intrinsic_breakdown,
        "blocked_reason_breakdown": intrinsic_breakdown,
    }
    if final_allowed is not None:
        final = final_allowed.fillna(False).astype(bool)
        counters["final_allowed_count_after_context"] = int(final.sum())
        counters["final_blocked_count_after_context"] = int((~final).sum())
        counters["allowed_count"] = counters["final_allowed_count_after_context"]
        counters["blocked_count"] = counters["final_blocked_count_after_context"]
    else:
        counters["allowed_count"] = counters["intrinsic_allowed_count"]
        counters["blocked_count"] = counters["intrinsic_blocked_count"]
    return counters
