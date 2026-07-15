"""Blocker components for ema_pullback StrategySpec pipeline."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.spec import BlockerRuleSpec
from research.strategies.ema_pullback.spec import TradeSide


def no_blockers(
    df: pd.DataFrame,
    side: TradeSide = "long",
    **_: object,
) -> pd.Series:
    """No blockers: pass all rows."""

    _ = side
    return pd.Series(True, index=df.index, dtype=bool)


def no_blockers_trace(
    df: pd.DataFrame,
    side: TradeSide = "long",
    **_: object,
) -> dict[str, pd.Series]:
    _ = side
    allowed = pd.Series(True, index=df.index, dtype=bool)
    return {"allowed": allowed}


def counter_candle_blocker_trace(
    df: pd.DataFrame,
    side: TradeSide = "long",
    **_: object,
) -> dict[str, pd.Series]:
    """Internals for counter_candle_blocker."""

    open_ = df["open"].astype(float)
    close = df["close"].astype(float)
    if side == "long":
        allowed = close >= open_
    elif side == "short":
        allowed = close <= open_
    else:
        raise ValueError("side must be 'long' or 'short'")
    allowed = allowed.fillna(False).astype(bool)
    return {"allowed": allowed}


def counter_candle_blocker(
    df: pd.DataFrame,
    side: TradeSide = "long",
    **_: object,
) -> pd.Series:
    """Allow entries only when the candle is not counter to the requested side."""

    return counter_candle_blocker_trace(df, side=side)["allowed"]


def rsi_lookback_extreme_blocker_trace(
    df: pd.DataFrame,
    side: TradeSide = "long",
    *,
    rule: BlockerRuleSpec,
    rsi_col: str | None = None,
) -> dict[str, pd.Series]:
    """Internals for rsi_lookback_extreme_blocker."""

    if rule.rsi is None or rsi_col is None:
        raise ValueError("rsi_lookback_extreme_blocker requires rule.rsi and rsi_col")
    rsi = df[rsi_col].astype(float)
    if side == "long":
        if rule.long_block_above is None:
            raise ValueError(
                "rsi_lookback_extreme_blocker requires long_block_above for long side"
            )
        extreme_seen = rsi > float(rule.long_block_above)
    elif side == "short":
        if rule.short_block_below is None:
            raise ValueError(
                "rsi_lookback_extreme_blocker requires short_block_below for short side"
            )
        extreme_seen = rsi < float(rule.short_block_below)
    else:
        raise ValueError("side must be 'long' or 'short'")

    if rule.lookback > 1:
        extreme_seen = extreme_seen.rolling(window=rule.lookback, min_periods=1).max().astype(bool)
    else:
        extreme_seen = extreme_seen.fillna(False).astype(bool)
    allowed = (~extreme_seen).astype(bool)
    return {
        "rsi": rsi,
        "extreme_seen": extreme_seen,
        "allowed": allowed,
    }


def rsi_lookback_extreme_blocker(
    df: pd.DataFrame,
    side: TradeSide = "long",
    *,
    rule: BlockerRuleSpec,
    rsi_col: str | None = None,
) -> pd.Series:
    """Block entries after overbought-extreme (long) or oversold-extreme (short) in lookback."""

    return rsi_lookback_extreme_blocker_trace(
        df, side=side, rule=rule, rsi_col=rsi_col
    )["allowed"]


from research.strategies.ema_pullback.components.trend_strength_episode import (  # noqa: E402
    build_trend_strength_blocker_counters,
    trend_strength_episode_blocker,
    trend_strength_episode_blocker_trace,
)

__all__ = [
    "no_blockers",
    "no_blockers_trace",
    "counter_candle_blocker",
    "counter_candle_blocker_trace",
    "rsi_lookback_extreme_blocker",
    "rsi_lookback_extreme_blocker_trace",
    "trend_strength_episode_blocker",
    "trend_strength_episode_blocker_trace",
    "build_trend_strength_blocker_counters",
]
