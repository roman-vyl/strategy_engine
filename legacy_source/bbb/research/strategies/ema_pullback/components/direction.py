"""Direction components for ema_pullback StrategySpec pipeline."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.spec import TradeSide


def ema_anchor_stack_trend_trace(
    df: pd.DataFrame,
    fast_col: str,
    anchor_col: str,
    slow_col: str,
    side: TradeSide = "long",
) -> dict[str, pd.Series]:
    """Per-bar internals for ema_anchor_stack_trend."""

    fast = df[fast_col].astype(float)
    anchor = df[anchor_col].astype(float)
    slow = df[slow_col].astype(float)
    if side == "long":
        fast_gt_anchor = fast > anchor
        anchor_gt_slow = anchor > slow
        direction_ok = fast_gt_anchor & anchor_gt_slow
    elif side == "short":
        fast_gt_anchor = fast < anchor
        anchor_gt_slow = anchor < slow
        direction_ok = fast_gt_anchor & anchor_gt_slow
    else:
        raise ValueError("side must be 'long' or 'short'")
    return {
        "fast_gt_anchor": fast_gt_anchor.fillna(False).astype(bool),
        "anchor_gt_slow": anchor_gt_slow.fillna(False).astype(bool),
        "direction_ok": direction_ok.fillna(False).astype(bool),
    }


def ema_anchor_stack_trend(
    df: pd.DataFrame,
    fast_col: str,
    anchor_col: str,
    slow_col: str,
    side: TradeSide = "long",
) -> pd.Series:
    """Direction is valid when the anchor stack matches the requested side."""

    return ema_anchor_stack_trend_trace(df, fast_col, anchor_col, slow_col, side=side)["direction_ok"]
