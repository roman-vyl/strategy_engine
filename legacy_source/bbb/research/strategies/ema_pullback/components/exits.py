"""Exit components for ema_pullback StrategySpec pipeline."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.spec import ExitRuleSpec
from research.strategies.ema_pullback.spec import TradeSide


def _consecutive_true(condition: pd.Series, confirm_bars: int) -> pd.Series:
    if confirm_bars < 1:
        raise ValueError("confirm_bars must be >= 1")
    cond = condition.fillna(False).astype(bool)
    if confirm_bars == 1:
        return cond
    return (
        cond.astype(int)
        .rolling(confirm_bars, min_periods=confirm_bars)
        .min()
        .fillna(0)
        .astype(bool)
    )


def no_signal_exit(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    **kwargs: object,
) -> pd.Series:
    _ = kwargs
    """No signal exit: always False (exits handled by stop/take)."""

    _ = anchor_col
    _ = side
    return pd.Series(False, index=df.index, dtype=bool)


def rsi_signal_exit(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    *,
    rule: ExitRuleSpec,
    rsi_col: str | None = None,
    **kwargs: object,
) -> pd.Series:
    _ = kwargs
    """Exit when prepared RSI reaches the configured side-aware threshold."""

    _ = anchor_col
    if rule.rsi is None or rsi_col is None:
        raise ValueError("rsi_signal_exit requires rule.rsi and rsi_col")
    rsi = df[rsi_col].astype(float)
    if side == "long":
        if rule.long_exit_above is None:
            raise ValueError("rsi_signal_exit requires long_exit_above for long side")
        out = rsi > float(rule.long_exit_above)
    elif side == "short":
        if rule.short_exit_below is None:
            raise ValueError("rsi_signal_exit requires short_exit_below for short side")
        out = rsi < float(rule.short_exit_below)
    else:
        raise ValueError("side must be 'long' or 'short'")
    return out.fillna(False).astype(bool)


def rsi_signal_exit_trace(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    *,
    rule: ExitRuleSpec,
    rsi_col: str | None = None,
    **kwargs: object,
) -> dict[str, pd.Series]:
    """Internals for rsi_signal_exit (aligned base-index series)."""

    _ = anchor_col
    _ = kwargs
    if rule.rsi is None or rsi_col is None:
        raise ValueError("rsi_signal_exit requires rule.rsi and rsi_col")
    rsi = df[rsi_col].astype(float)
    if side == "long":
        if rule.long_exit_above is None:
            raise ValueError("rsi_signal_exit requires long_exit_above for long side")
        exit_fired = rsi > float(rule.long_exit_above)
        condition_key = "exit_above"
        threshold = float(rule.long_exit_above)
    elif side == "short":
        if rule.short_exit_below is None:
            raise ValueError("rsi_signal_exit requires short_exit_below for short side")
        exit_fired = rsi < float(rule.short_exit_below)
        condition_key = "exit_below"
        threshold = float(rule.short_exit_below)
    else:
        raise ValueError("side must be 'long' or 'short'")
    return {
        "rsi": rsi,
        "exit_fired": exit_fired.fillna(False).astype(bool),
        "condition": pd.Series(condition_key, index=df.index, dtype=object),
        "threshold": pd.Series(threshold, index=df.index, dtype=float),
    }


def ema_close_loss_exit(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    *,
    rule: ExitRuleSpec,
    ema_col: str | None = None,
    **_: object,
) -> pd.Series:
    """Exit when base close violates aligned EMA for confirm_bars consecutive base bars."""

    _ = anchor_col
    if rule.ema is None or ema_col is None:
        raise ValueError("ema_close_loss_exit requires rule.ema and ema_col")
    close = df["close"].astype(float)
    ema = df[ema_col].astype(float)
    if side == "long":
        condition = close < ema
    elif side == "short":
        condition = close > ema
    else:
        raise ValueError("side must be 'long' or 'short'")
    return _consecutive_true(condition, rule.confirm_bars)


def ema_cross_loss_exit(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    *,
    rule: ExitRuleSpec,
    fast_col: str | None = None,
    slow_col: str | None = None,
    **_: object,
) -> pd.Series:
    """Exit on fast/slow EMA cross on base index.

    confirm_bars=1: classic cross (prior bar had opposite ordering).
    confirm_bars>1: adverse hold for N base bars AND cross within rolling N-bar window.
    """

    _ = anchor_col
    if rule.fast_ema is None or fast_col is None or slow_col is None:
        raise ValueError("ema_cross_loss_exit requires rule.fast_ema, fast_col, and slow_col")
    fast = df[fast_col].astype(float)
    slow = df[slow_col].astype(float)
    if rule.confirm_bars == 1:
        prev_fast = fast.shift(1)
        prev_slow = slow.shift(1)
        if side == "long":
            out = (fast < slow) & (prev_fast >= prev_slow)
        elif side == "short":
            out = (fast > slow) & (prev_fast <= prev_slow)
        else:
            raise ValueError("side must be 'long' or 'short'")
        return out.fillna(False).astype(bool)

    prev_fast = fast.shift(1)
    prev_slow = slow.shift(1)
    if side == "long":
        cross = (fast < slow) & (prev_fast >= prev_slow)
        adverse = fast < slow
    elif side == "short":
        cross = (fast > slow) & (prev_fast <= prev_slow)
        adverse = fast > slow
    else:
        raise ValueError("side must be 'long' or 'short'")
    cross = cross.fillna(False).astype(bool)
    adverse_hold = _consecutive_true(adverse, rule.confirm_bars)
    cross_in_window = (
        cross.astype(int).rolling(rule.confirm_bars, min_periods=1).max().fillna(0).astype(bool)
    )
    return (adverse_hold & cross_in_window).astype(bool)


def atr_distance_exit(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    *,
    rule: ExitRuleSpec,
    distance_col: str | None = None,
) -> pd.Series:
    """Return a prepared ATR-based distance series for stop/take exits."""

    _ = anchor_col
    _ = side
    if rule.distance is None or distance_col is None:
        raise ValueError("atr_distance_exit requires rule.distance and distance_col")
    return df[distance_col].astype(float)


def constant_usd_distance_exit(
    df: pd.DataFrame,
    anchor_col: str | None = None,
    side: TradeSide = "long",
    *,
    rule: ExitRuleSpec,
    distance_col: str | None = None,
) -> pd.Series:
    """Constant stop/take distance in USD (same numeric units as ``close`` on *USDT markets)."""

    _ = anchor_col
    _ = side
    _ = distance_col
    if rule.usd_distance is None:
        raise ValueError("constant_usd_distance_exit requires rule.usd_distance")
    return pd.Series(float(rule.usd_distance), index=df.index, dtype=float)
