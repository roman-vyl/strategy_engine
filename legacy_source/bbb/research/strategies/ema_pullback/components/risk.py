"""Risk filter components for ema_pullback StrategySpec pipeline."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.spec import TradeSide


def no_risk_filter(df: pd.DataFrame, side: TradeSide = "long") -> pd.Series:
    """No risk filter: pass all rows."""

    _ = side
    return pd.Series(True, index=df.index, dtype=bool)
