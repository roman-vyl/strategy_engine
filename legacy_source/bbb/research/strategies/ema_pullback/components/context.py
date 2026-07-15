"""HTF context component for exit policy profile selection."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class HtfContextMasks:
    up: pd.Series
    down: pd.Series
    neutral: pd.Series

    def state_series(self) -> pd.Series:
        state = pd.Series("neutral", index=self.up.index, dtype="object")
        state.loc[self.up.fillna(False)] = "up"
        state.loc[self.down.fillna(False)] = "down"
        return state


def htf_context(
    df: pd.DataFrame,
    *,
    fast_col: str,
    anchor_col: str,
    slow_col: str,
) -> HtfContextMasks:
    fast = df[fast_col].astype(float)
    anchor = df[anchor_col].astype(float)
    slow = df[slow_col].astype(float)
    has_nan = fast.isna() | anchor.isna() | slow.isna()

    up = (fast > anchor) & (anchor > slow) & (~has_nan)
    down = (fast < anchor) & (anchor < slow) & (~has_nan)
    neutral = (~up) & (~down)

    return HtfContextMasks(
        up=up.fillna(False).astype(bool),
        down=down.fillna(False).astype(bool),
        neutral=neutral.fillna(True).astype(bool),
    )

