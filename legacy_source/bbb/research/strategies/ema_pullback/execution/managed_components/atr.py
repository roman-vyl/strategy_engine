from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.strategies.ema_pullback.spec import ManagementAtrRefSpec


def management_atr_key(
    *,
    atr_period: int,
    atr: ManagementAtrRefSpec | None,
) -> tuple[str, int]:
    if atr is not None:
        return (atr.timeframe, atr.period)
    return ("base", atr_period)


def atr_value_at_bar(
    *,
    bar_index: int,
    atr_period: int,
    atr: ManagementAtrRefSpec | None,
    atr_series_by_key: dict[tuple[str, int], pd.Series],
) -> float | None:
    key = management_atr_key(atr_period=atr_period, atr=atr)
    series = atr_series_by_key.get(key)
    if series is None or not (0 <= bar_index < len(series)):
        return None
    try:
        value = float(series.iloc[bar_index])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out
