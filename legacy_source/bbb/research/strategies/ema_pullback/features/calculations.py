"""Feature columns from OHLCV DataFrame only (no IO, no vectorbt)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_engine.contracts import pandas_freq_alias
from research.strategies.ema_pullback.features.plan import FeaturePlan


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    h_l = high - low
    h_pc = (high - prev_close).abs()
    l_pc = (low - prev_close).abs()
    return pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)


def _atr_rolling_mean(high: pd.Series, low: pd.Series, close: pd.Series, *, period: int) -> pd.Series:
    tr = _true_range(high, low, close)
    return tr.rolling(window=period, min_periods=period).mean()


def _rsi_rolling_mean(close: pd.Series, *, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _wilder_rma(series: pd.Series, *, period: int) -> pd.Series:
    """Wilder RMA; first output at the earliest index with `period` finite samples."""

    values = series.astype(float).to_numpy()
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return pd.Series(out, index=series.index, dtype=float)

    start_idx: int | None = None
    for end in range(period - 1, n):
        window = values[end - period + 1 : end + 1]
        if np.all(np.isfinite(window)):
            start_idx = end
            break
    if start_idx is None:
        return pd.Series(out, index=series.index, dtype=float)

    out[start_idx] = float(np.mean(values[start_idx - period + 1 : start_idx + 1]))
    for i in range(start_idx + 1, n):
        prev = out[i - 1]
        current = values[i]
        if not np.isfinite(prev) or not np.isfinite(current):
            out[i] = np.nan
            continue
        out[i] = ((prev * (period - 1)) + current) / period

    return pd.Series(out, index=series.index, dtype=float)


def _compute_adx_dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    period: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(0.0, index=high.index, dtype=float)
    minus_dm = pd.Series(0.0, index=high.index, dtype=float)
    plus_mask = (up_move > down_move) & (up_move > 0)
    minus_mask = (down_move > up_move) & (down_move > 0)
    plus_dm.loc[plus_mask] = up_move.loc[plus_mask]
    minus_dm.loc[minus_mask] = down_move.loc[minus_mask]

    tr = _true_range(high, low, close)
    smooth_tr = _wilder_rma(tr, period=period)
    smooth_plus = _wilder_rma(plus_dm, period=period)
    smooth_minus = _wilder_rma(minus_dm, period=period)

    di_plus = 100.0 * smooth_plus / smooth_tr
    di_minus = 100.0 * smooth_minus / smooth_tr
    di_sum = di_plus + di_minus
    dx = 100.0 * (di_plus - di_minus).abs() / di_sum.replace(0, float("nan"))
    adx = _wilder_rma(dx, period=period)

    di_warmup = period
    di_plus.iloc[:di_warmup] = np.nan
    di_minus.iloc[:di_warmup] = np.nan

    return adx, di_plus, di_minus


def _resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    freq = pandas_freq_alias(timeframe)
    resampled = df.resample(freq, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return resampled.dropna(subset=["open", "high", "low", "close"])


def _align_completed_feature_to_base(
    feature: pd.Series,
    *,
    timeframe: str,
    base_index: pd.Index,
) -> pd.Series:
    freq = pandas_freq_alias(timeframe)
    completed = feature.copy()
    completed.index = completed.index + pd.tseries.frequencies.to_offset(freq)
    return completed.reindex(base_index, method="ffill")


def add_feature_columns_from_plan(df: pd.DataFrame, plan: FeaturePlan) -> pd.DataFrame:
    out = df.copy()
    frames: dict[str, pd.DataFrame] = {"base": out}
    computed_adx_dmi: set[tuple[str, int]] = set()

    for feature in plan.features:
        feature_frame = frames.get(feature.timeframe)
        if feature_frame is None:
            feature_frame = _resample_ohlcv(out, feature.timeframe)
            frames[feature.timeframe] = feature_frame
        close = feature_frame["close"].astype(float)
        high = feature_frame["high"].astype(float)
        low = feature_frame["low"].astype(float)
        if feature.kind == "ema":
            assert feature.period is not None
            values = close.ewm(span=feature.period, adjust=False).mean()
            if feature.timeframe != "base":
                values = _align_completed_feature_to_base(
                    values,
                    timeframe=feature.timeframe,
                    base_index=out.index,
                )
            out[feature.feature_id] = values
            continue
        if feature.kind == "atr":
            assert feature.period is not None
            values = _atr_rolling_mean(high, low, close, period=feature.period)
            if feature.timeframe != "base":
                values = _align_completed_feature_to_base(
                    values,
                    timeframe=feature.timeframe,
                    base_index=out.index,
                )
            out[feature.feature_id] = values
            continue
        if feature.kind == "atr_distance":
            if feature.base_feature_id is None or feature.multiplier is None:
                raise ValueError("atr_distance planned feature requires base_feature_id and multiplier")
            out[feature.feature_id] = out[feature.base_feature_id].astype(float) * float(feature.multiplier)
            continue
        if feature.kind == "rsi":
            assert feature.period is not None
            values = _rsi_rolling_mean(close, period=feature.period)
            if feature.timeframe != "base":
                values = _align_completed_feature_to_base(
                    values,
                    timeframe=feature.timeframe,
                    base_index=out.index,
                )
            out[feature.feature_id] = values
            continue
        if feature.kind in {"adx", "di_plus", "di_minus"}:
            assert feature.period is not None
            key = (feature.timeframe, feature.period)
            if key in computed_adx_dmi:
                continue
            adx, di_plus, di_minus = _compute_adx_dmi(
                high, low, close, period=feature.period
            )
            if feature.timeframe != "base":
                adx = _align_completed_feature_to_base(
                    adx, timeframe=feature.timeframe, base_index=out.index
                )
                di_plus = _align_completed_feature_to_base(
                    di_plus, timeframe=feature.timeframe, base_index=out.index
                )
                di_minus = _align_completed_feature_to_base(
                    di_minus, timeframe=feature.timeframe, base_index=out.index
                )
            from research.strategies.ema_pullback.features.plan import (
                _adx_feature_id,
                _di_minus_feature_id,
                _di_plus_feature_id,
            )

            out[_adx_feature_id(feature.timeframe, feature.period)] = adx
            out[_di_plus_feature_id(feature.timeframe, feature.period)] = di_plus
            out[_di_minus_feature_id(feature.timeframe, feature.period)] = di_minus
            computed_adx_dmi.add(key)
            continue
        raise ValueError(f"unsupported feature kind: {feature.kind!r}")
    return out
