"""BBB-compatible ADX and Directional Movement Index implementation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.implementations.atr import true_range

_ADX_KINDS = {"adx", "di_plus", "di_minus"}


def validate_adx_dmi_feature(feature: PlannedFeature) -> None:
    if feature.kind not in _ADX_KINDS:
        raise InvalidRequestError(
            "ADX/DMI feature kind must be adx, di_plus, or di_minus",
            output_id=feature.output_id,
            kind=feature.kind,
        )
    if feature.source != "close":
        raise InvalidRequestError(
            "ADX/DMI source must be close for BBB compatibility",
            output_id=feature.output_id,
            source=feature.source,
        )
    period = feature.parameters.get("period")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise InvalidRequestError(
            "ADX/DMI period must be a positive integer",
            output_id=feature.output_id,
            period=period,
        )
    if set(feature.parameters) != {"period"}:
        raise InvalidRequestError(
            "ADX/DMI parameters must contain only period",
            output_id=feature.output_id,
            parameters=sorted(feature.parameters),
        )
    if feature.dependencies:
        raise InvalidRequestError(
            "ADX/DMI does not accept feature dependencies",
            output_id=feature.output_id,
        )


def wilder_rma(series: pd.Series, *, period: int) -> pd.Series:
    """Match BBB Wilder RMA bootstrap and recursive update semantics."""

    values = series.astype(float).to_numpy()
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < period:
        return pd.Series(out, index=series.index, dtype=float)

    start_idx: int | None = None
    for end in range(period - 1, len(values)):
        window = values[end - period + 1 : end + 1]
        if np.all(np.isfinite(window)):
            start_idx = end
            break
    if start_idx is None:
        return pd.Series(out, index=series.index, dtype=float)

    out[start_idx] = float(np.mean(values[start_idx - period + 1 : start_idx + 1]))
    for index in range(start_idx + 1, len(values)):
        previous = out[index - 1]
        current = values[index]
        if not np.isfinite(previous) or not np.isfinite(current):
            continue
        out[index] = ((previous * (period - 1)) + current) / period
    return pd.Series(out, index=series.index, dtype=float)


def compute_adx_dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    period: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return ADX, DI+, and DI- with exact BBB warmup semantics."""

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(0.0, index=high.index, dtype=float)
    minus_dm = pd.Series(0.0, index=high.index, dtype=float)
    plus_mask = (up_move > down_move) & (up_move > 0)
    minus_mask = (down_move > up_move) & (down_move > 0)
    plus_dm.loc[plus_mask] = up_move.loc[plus_mask]
    minus_dm.loc[minus_mask] = down_move.loc[minus_mask]

    smooth_tr = wilder_rma(true_range(high, low, close), period=period)
    smooth_plus = wilder_rma(plus_dm, period=period)
    smooth_minus = wilder_rma(minus_dm, period=period)

    di_plus = 100.0 * smooth_plus / smooth_tr
    di_minus = 100.0 * smooth_minus / smooth_tr
    di_sum = di_plus + di_minus
    dx = 100.0 * (di_plus - di_minus).abs() / di_sum.replace(0, float("nan"))
    adx = wilder_rma(dx, period=period)

    di_plus.iloc[:period] = np.nan
    di_minus.iloc[:period] = np.nan
    return adx, di_plus, di_minus
