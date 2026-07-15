"""Post-trade quality diagnostics for ema_pullback closed trades."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Literal

import pandas as pd

from research.strategies.ema_pullback.execution.exit_attribution import (
    ExitAttributionContext,
    _agg_sl_tp_at_entry,
    _levels_from_ratios,
    _resolve_profile,
    _stop_hit_long,
    _stop_hit_short,
)

_REFERENCE_PROFILE_KEYS = frozenset({"aligned", "countertrend", "neutral"})


QUALITY_FLAGS = (
    "high_mfe_high_capture",
    "high_mfe_low_capture",
    "signal_exit_winner",
    "signal_exit_giveback_failure",
    "stop_loss_after_low_mfe",
    "stop_loss_after_bad_context",
)

FirstLevelHit = Literal["take_profit", "stop_loss", "ambiguous_same_bar", "none"]


@dataclass(frozen=True)
class TradeQualityConfig:
    schema: str = "trade-exit-quality-diagnostics-v1"
    high_mfe_atr: float = 2.0
    high_mfe_pct_fallback: float = 0.02
    high_capture_ratio: float = 0.60
    low_capture_ratio: float = 0.30
    low_mfe_atr: float = 1.0
    low_mfe_pct_fallback: float = 0.005
    giveback_failure_atr: float = 1.5
    atr_source: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_TRADE_QUALITY_CONFIG = TradeQualityConfig()


def trade_quality_config_payload(*, atr_source: str | None = None) -> dict[str, Any]:
    return TradeQualityConfig(atr_source=atr_source).to_payload()


def path_diagnostics_config_payload() -> dict[str, Any]:
    return {
        "schema": "trade_path_diagnostics",
        "version": "1",
        "window": "entry_to_exit_inclusive",
        "open_trades": "omitted",
        "same_bar_level_policy": "ambiguous_same_bar",
        "post_exit_bars": "excluded",
    }


@dataclass(frozen=True)
class TradePathCore:
    mfe_price: float
    mfe_pct: float
    mfe_bar_idx: int
    mfe_bars_from_entry: int
    mae_price: float
    mae_pct: float
    mae_bar_idx: int
    mae_bars_from_entry: int
    realized_favorable_move: float
    captured_pct: float
    capture_ratio: float | None
    giveback_price: float | None
    giveback_pct: float | None
    bars_from_mfe_to_exit: int


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _ratio_or_none(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _bar_time_ms(index: pd.Index | None, bar_idx: int) -> int | None:
    if index is None or bar_idx < 0 or bar_idx >= len(index):
        return None
    ts = index[bar_idx]
    if isinstance(ts, pd.Timestamp):
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return int(ts.value // 1_000_000)
    try:
        v = int(ts)
    except (TypeError, ValueError):
        v = None
    if v is not None and not isinstance(ts, bool):
        # DB OHLCV uses open_time_ms; raw int index values are ms, not ns.
        if v >= 1_000_000_000_000:
            return v
        if v >= 1_000_000_000:
            return v * 1000
    parsed = pd.Timestamp(ts)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    else:
        parsed = parsed.tz_convert("UTC")
    return int(parsed.value // 1_000_000)


def _resolve_reference_profile(record: dict[str, Any]) -> str | None:
    """Locked entry profile for SL/TP agg lookup (not exit-rule metadata alone)."""

    for key in ("entry_profile", "active_exit_profile", "exit_profile"):
        raw = record.get(key)
        if isinstance(raw, str) and raw in _REFERENCE_PROFILE_KEYS:
            return raw
    ctx_state = record.get("entry_context_state")
    direction = str(record.get("direction") or "")
    if ctx_state in {"up", "down", "neutral"}:
        return _resolve_profile(direction, str(ctx_state))
    return None


def _entry_atr(
    diagnostic_atr_series: pd.Series | None,
    entry_idx: int,
) -> float | None:
    if diagnostic_atr_series is None or entry_idx < 0 or entry_idx >= len(diagnostic_atr_series):
        return None
    value = _finite_float(diagnostic_atr_series.iloc[entry_idx])
    if value is None or value <= 0.0:
        return None
    return value


def _is_stop_loss_exit(record: dict[str, Any]) -> bool:
    exit_kind = record.get("exit_kind")
    if exit_kind == "stop_loss":
        return True
    exit_reason = str(record.get("exit_reason") or "")
    if exit_reason.startswith("stop_loss:"):
        return True
    component_id = str(record.get("exit_component_id") or "")
    return "stop_loss" in component_id


def _bad_context_for_direction(direction: str, entry_context_state: Any) -> bool:
    if direction == "long":
        return entry_context_state in {"down", "neutral"}
    if direction == "short":
        return entry_context_state in {"up", "neutral"}
    return False


def _high_mfe(metrics: dict[str, Any], config: TradeQualityConfig) -> bool:
    mfe_atr = metrics.get("mfe_atr")
    if mfe_atr is not None:
        return float(mfe_atr) >= config.high_mfe_atr
    mfe_pct = metrics.get("mfe_pct")
    return mfe_pct is not None and float(mfe_pct) >= config.high_mfe_pct_fallback


def _low_mfe(metrics: dict[str, Any], config: TradeQualityConfig) -> bool:
    mfe_atr = metrics.get("mfe_atr")
    if mfe_atr is not None:
        return float(mfe_atr) < config.low_mfe_atr
    mfe_pct = metrics.get("mfe_pct")
    return mfe_pct is not None and float(mfe_pct) < config.low_mfe_pct_fallback


def _large_giveback(metrics: dict[str, Any], config: TradeQualityConfig) -> bool:
    giveback_atr = metrics.get("giveback_atr")
    return giveback_atr is not None and float(giveback_atr) >= config.giveback_failure_atr


def classify_quality_flags(
    record: dict[str, Any],
    metrics: dict[str, Any],
    *,
    config: TradeQualityConfig = DEFAULT_TRADE_QUALITY_CONFIG,
) -> list[str]:
    """Return additive v1 quality flags for one closed trade."""

    flags: list[str] = []
    high_mfe = _high_mfe(metrics, config)
    low_mfe = _low_mfe(metrics, config)
    capture_ratio = metrics.get("capture_ratio")
    high_capture = capture_ratio is not None and float(capture_ratio) >= config.high_capture_ratio
    low_capture = capture_ratio is not None and float(capture_ratio) < config.low_capture_ratio
    captured_price = metrics.get("captured_price")
    is_signal_exit = record.get("exit_kind") == "signal"
    is_stop_loss = _is_stop_loss_exit(record)

    if high_mfe and high_capture:
        flags.append("high_mfe_high_capture")
    if high_mfe and low_capture:
        flags.append("high_mfe_low_capture")
    if is_signal_exit and captured_price is not None and float(captured_price) > 0.0 and high_capture:
        flags.append("signal_exit_winner")
    if is_signal_exit and high_mfe and (low_capture or _large_giveback(metrics, config)):
        flags.append("signal_exit_giveback_failure")
    if is_stop_loss and low_mfe:
        flags.append("stop_loss_after_low_mfe")
    if is_stop_loss and _bad_context_for_direction(
        str(record.get("direction") or ""),
        record.get("entry_context_state"),
    ):
        flags.append("stop_loss_after_bad_context")
    return flags


def _compute_trade_path_core(
    *,
    direction: str,
    entry_price: float,
    exit_price: float,
    entry_idx: int,
    exit_idx: int,
    high: pd.Series,
    low: pd.Series,
) -> TradePathCore:
    if entry_idx < 0 or exit_idx < entry_idx or exit_idx >= len(high) or exit_idx >= len(low):
        raise ValueError("invalid entry/exit indices for trade quality diagnostics")
    if entry_price <= 0.0:
        raise ValueError("entry_price must be positive for trade quality diagnostics")

    high_span = high.iloc[entry_idx : exit_idx + 1].astype(float)
    low_span = low.iloc[entry_idx : exit_idx + 1].astype(float)
    if high_span.isna().any() or low_span.isna().any():
        raise ValueError("high/low span contains NaN for trade quality diagnostics")

    if direction == "long":
        favorable = high_span - entry_price
        adverse = entry_price - low_span
        realized = exit_price - entry_price
    elif direction == "short":
        favorable = entry_price - low_span
        adverse = high_span - entry_price
        realized = entry_price - exit_price
    else:
        raise ValueError(f"unsupported trade direction: {direction!r}")

    mfe_offset = int(favorable.to_numpy().argmax())
    mae_offset = int(adverse.to_numpy().argmax())
    raw_mfe_price = float(favorable.iloc[mfe_offset])
    raw_mae_price = float(adverse.iloc[mae_offset])

    if raw_mfe_price <= 0.0:
        mfe_price = 0.0
        mfe_offset = 0
    else:
        mfe_price = raw_mfe_price

    if raw_mae_price <= 0.0:
        mae_price = 0.0
        mae_offset = 0
    else:
        mae_price = raw_mae_price

    capture_ratio = realized / mfe_price if mfe_price > 0.0 else None
    if mfe_price > 0.0:
        giveback_price = max(0.0, mfe_price - realized)
        giveback_pct = giveback_price / entry_price
    else:
        giveback_price = None
        giveback_pct = None

    mfe_bar_idx = entry_idx + mfe_offset
    mae_bar_idx = entry_idx + mae_offset

    return TradePathCore(
        mfe_price=mfe_price,
        mfe_pct=mfe_price / entry_price,
        mfe_bar_idx=mfe_bar_idx,
        mfe_bars_from_entry=mfe_offset,
        mae_price=mae_price,
        mae_pct=mae_price / entry_price,
        mae_bar_idx=mae_bar_idx,
        mae_bars_from_entry=mae_offset,
        realized_favorable_move=realized,
        captured_pct=realized / entry_price,
        capture_ratio=capture_ratio,
        giveback_price=giveback_price,
        giveback_pct=giveback_pct,
        bars_from_mfe_to_exit=exit_idx - mfe_bar_idx,
    )


def _flat_fields_from_core(
    core: TradePathCore,
    *,
    entry_idx: int,
    diagnostic_atr_series: pd.Series | None = None,
) -> dict[str, Any]:
    entry_atr = _entry_atr(diagnostic_atr_series, entry_idx)
    return {
        "mfe_price": core.mfe_price,
        "mfe_pct": core.mfe_pct,
        "mfe_atr": _ratio_or_none(core.mfe_price, entry_atr),
        "mae_price": core.mae_price,
        "mae_pct": core.mae_pct,
        "mae_atr": _ratio_or_none(core.mae_price, entry_atr),
        "bars_to_mfe": core.mfe_bars_from_entry,
        "bars_to_mae": core.mae_bars_from_entry,
        "captured_price": core.realized_favorable_move,
        "captured_pct": core.captured_pct,
        "captured_atr": _ratio_or_none(core.realized_favorable_move, entry_atr),
        "capture_ratio": core.capture_ratio,
        "giveback_price": core.giveback_price,
        "giveback_pct": core.giveback_pct,
        "giveback_atr": _ratio_or_none(core.giveback_price, entry_atr),
        "bars_from_mfe_to_exit": core.bars_from_mfe_to_exit,
    }


def _build_nested_path_diagnostics(
    core: TradePathCore,
    *,
    index: pd.Index | None = None,
) -> dict[str, Any]:
    return {
        "mfe": {
            "price_move": core.mfe_price,
            "pct": core.mfe_pct,
            "time_ms": _bar_time_ms(index, core.mfe_bar_idx),
            "bars_from_entry": core.mfe_bars_from_entry,
        },
        "mae": {
            "price_move": core.mae_price,
            "pct": core.mae_pct,
            "time_ms": _bar_time_ms(index, core.mae_bar_idx),
            "bars_from_entry": core.mae_bars_from_entry,
        },
        "capture": {
            "capture_ratio": core.capture_ratio,
            "captured_pct": core.captured_pct,
            "giveback_price": core.giveback_price,
            "giveback_pct": core.giveback_pct,
            "bars_from_mfe_to_exit": core.bars_from_mfe_to_exit,
        },
    }


def _tp_touched(
    direction: str,
    *,
    open_: float,
    high: float,
    low: float,
    tp_level: float,
) -> bool:
    if direction == "long":
        return _stop_hit_long(open_, high, low, tp_level, is_loss=False)
    return _stop_hit_short(open_, high, low, tp_level, is_loss=False)


def _sl_touched(
    direction: str,
    *,
    open_: float,
    high: float,
    low: float,
    sl_level: float,
) -> bool:
    if direction == "long":
        return _stop_hit_long(open_, high, low, sl_level, is_loss=True)
    return _stop_hit_short(open_, high, low, sl_level, is_loss=True)


def _compute_reference_levels(
    *,
    direction: str,
    entry_price: float,
    entry_idx: int,
    exit_idx: int,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series | None,
    close: pd.Series | None,
    attribution: ExitAttributionContext | None,
    profile: str | None,
    index: pd.Index | None = None,
) -> dict[str, Any]:
    unavailable: dict[str, Any] = {
        "reference_levels_available": False,
        "initial_stop_price": None,
        "initial_take_profit_price": None,
        "initial_risk_price_move": None,
        "initial_reward_price_move": None,
        "reached_initial_tp": False,
        "reached_initial_sl": False,
        "first_level_hit": "none",
        "first_level_hit_time_ms": None,
        "bars_to_first_level_hit": None,
    }

    if attribution is None or profile is None:
        return unavailable

    sl_r, tp_r = _agg_sl_tp_at_entry(attribution, entry_idx, profile=profile)
    stop_anchor: float | None = None
    if close is not None and 0 <= entry_idx < len(close):
        stop_anchor = _finite_float(close.iloc[entry_idx])
    if stop_anchor is None:
        stop_anchor = entry_price

    sl_level, tp_level = _levels_from_ratios(direction, stop_anchor, sl_r, tp_r)
    has_sl = sl_level is not None
    has_tp = tp_level is not None
    if not has_sl and not has_tp:
        return unavailable

    initial_stop = float(sl_level) if has_sl else None
    initial_tp = float(tp_level) if has_tp else None
    initial_risk = abs(entry_price - initial_stop) if initial_stop is not None else None
    initial_reward = abs(initial_tp - entry_price) if initial_tp is not None else None

    reached_tp = False
    reached_sl = False
    first_hit: FirstLevelHit = "none"
    first_hit_bar: int | None = None

    for bar_idx in range(entry_idx, exit_idx + 1):
        h = float(high.iloc[bar_idx])
        l = float(low.iloc[bar_idx])
        o = float(open_.iloc[bar_idx]) if open_ is not None else h

        tp_hit = initial_tp is not None and _tp_touched(
            direction, open_=o, high=h, low=l, tp_level=initial_tp
        )
        sl_hit = initial_stop is not None and _sl_touched(
            direction, open_=o, high=h, low=l, sl_level=initial_stop
        )

        if tp_hit:
            reached_tp = True
        if sl_hit:
            reached_sl = True

        if first_hit_bar is None and (tp_hit or sl_hit):
            if tp_hit and sl_hit:
                first_hit = "ambiguous_same_bar"
            elif tp_hit:
                first_hit = "take_profit"
            else:
                first_hit = "stop_loss"
            first_hit_bar = bar_idx

    bars_to_first = (first_hit_bar - entry_idx) if first_hit_bar is not None else None
    return {
        "reference_levels_available": True,
        "initial_stop_price": initial_stop,
        "initial_take_profit_price": initial_tp,
        "initial_risk_price_move": initial_risk,
        "initial_reward_price_move": initial_reward,
        "reached_initial_tp": reached_tp,
        "reached_initial_sl": reached_sl,
        "first_level_hit": first_hit,
        "first_level_hit_time_ms": _bar_time_ms(index, first_hit_bar) if first_hit_bar is not None else None,
        "bars_to_first_level_hit": bars_to_first,
    }


def compute_trade_quality_metrics(
    *,
    direction: str,
    entry_price: float,
    exit_price: float,
    entry_idx: int,
    exit_idx: int,
    high: pd.Series,
    low: pd.Series,
    diagnostic_atr_series: pd.Series | None = None,
) -> dict[str, Any]:
    """Compute direction-aware bar-level excursion and capture metrics (flat v5 fields)."""

    core = _compute_trade_path_core(
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        high=high,
        low=low,
    )
    return _flat_fields_from_core(core, entry_idx=entry_idx, diagnostic_atr_series=diagnostic_atr_series)


def build_trade_quality_diagnostics(
    record: dict[str, Any],
    *,
    entry_idx: int,
    exit_idx: int,
    high: pd.Series,
    low: pd.Series,
    index: pd.Index | None = None,
    open_: pd.Series | None = None,
    close: pd.Series | None = None,
    attribution: ExitAttributionContext | None = None,
    diagnostic_atr_series: pd.Series | None = None,
    config: TradeQualityConfig = DEFAULT_TRADE_QUALITY_CONFIG,
    include_nested: bool = True,
) -> dict[str, Any]:
    core = _compute_trade_path_core(
        direction=str(record["direction"]),
        entry_price=float(record["entry_price"]),
        exit_price=float(record["exit_price"]),
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        high=high,
        low=low,
    )
    out = _flat_fields_from_core(core, entry_idx=entry_idx, diagnostic_atr_series=diagnostic_atr_series)
    out["quality_flags"] = classify_quality_flags(record, out, config=config)

    if include_nested:
        out["path_diagnostics"] = _build_nested_path_diagnostics(core, index=index)
        profile = _resolve_reference_profile(record)
        out["reference_levels"] = _compute_reference_levels(
            direction=str(record["direction"]),
            entry_price=float(record["entry_price"]),
            entry_idx=entry_idx,
            exit_idx=exit_idx,
            high=high,
            low=low,
            open_=open_,
            close=close,
            attribution=attribution,
            profile=profile,
            index=index,
        )
    return out


def _avg_non_null(records: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite_float(record.get(key)) for record in records]
    non_null = [value for value in values if value is not None]
    if not non_null:
        return None
    return sum(non_null) / len(non_null)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return ordered[lo]
    weight = rank - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def _finite_values(records: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for record in records:
        value = _finite_float(record.get(key))
        if value is not None:
            out.append(value)
    return out


def _path_summary_bucket(records: list[dict[str, Any]]) -> dict[str, Any]:
    mfe_pcts = _finite_values(records, "mfe_pct")
    mae_pcts = _finite_values(records, "mae_pct")
    capture_ratios = _finite_values(records, "capture_ratio")
    giveback_pcts = _finite_values(records, "giveback_pct")
    bars_to_mfe = [float(record["bars_to_mfe"]) for record in records if record.get("bars_to_mfe") is not None]
    bars_to_mae = [float(record["bars_to_mae"]) for record in records if record.get("bars_to_mae") is not None]
    bars_to_first = [
        float(ref["bars_to_first_level_hit"])
        for record in records
        if (ref := record.get("reference_levels")) is not None
        and ref.get("bars_to_first_level_hit") is not None
    ]

    ref_available = 0
    ref_unavailable = 0
    reached_tp = 0
    reached_sl = 0
    first_tp = 0
    first_sl = 0
    ambiguous_first = 0
    no_ref_hit = 0
    for record in records:
        ref = record.get("reference_levels")
        if ref is None:
            continue
        if ref.get("reference_levels_available"):
            ref_available += 1
            if ref.get("reached_initial_tp"):
                reached_tp += 1
            if ref.get("reached_initial_sl"):
                reached_sl += 1
            first = ref.get("first_level_hit")
            if first == "take_profit":
                first_tp += 1
            elif first == "stop_loss":
                first_sl += 1
            elif first == "ambiguous_same_bar":
                ambiguous_first += 1
            elif first == "none":
                no_ref_hit += 1
        else:
            ref_unavailable += 1

    return {
        "trade_count": len(records),
        "avg_mfe_pct": _avg_non_null(records, "mfe_pct"),
        "median_mfe_pct": _median(mfe_pcts),
        "p75_mfe_pct": _percentile(mfe_pcts, 0.75),
        "p90_mfe_pct": _percentile(mfe_pcts, 0.90),
        "avg_mae_pct": _avg_non_null(records, "mae_pct"),
        "median_mae_pct": _median(mae_pcts),
        "p75_mae_pct": _percentile(mae_pcts, 0.75),
        "p90_mae_pct": _percentile(mae_pcts, 0.90),
        "avg_capture_ratio": _avg_non_null(records, "capture_ratio"),
        "median_capture_ratio": _median(capture_ratios),
        "avg_giveback_pct": _avg_non_null(records, "giveback_pct"),
        "median_giveback_pct": _median(giveback_pcts),
        "reference_levels_available_count": ref_available,
        "reference_levels_unavailable_count": ref_unavailable,
        "reached_initial_tp_count": reached_tp,
        "reached_initial_sl_count": reached_sl,
        "first_take_profit_count": first_tp,
        "first_stop_loss_count": first_sl,
        "ambiguous_first_level_count": ambiguous_first,
        "no_reference_level_hit_count": no_ref_hit,
        "avg_bars_to_mfe": (sum(bars_to_mfe) / len(bars_to_mfe)) if bars_to_mfe else None,
        "median_bars_to_mfe": _median(bars_to_mfe),
        "avg_bars_to_mae": (sum(bars_to_mae) / len(bars_to_mae)) if bars_to_mae else None,
        "median_bars_to_mae": _median(bars_to_mae),
        "avg_bars_to_first_level_hit": (sum(bars_to_first) / len(bars_to_first)) if bars_to_first else None,
        "median_bars_to_first_level_hit": _median(bars_to_first),
    }


def _closed_with_path_diagnostics(trade_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in trade_records
        if record.get("status") == "closed" and "path_diagnostics" in record
    ]


def build_path_diagnostics_summary(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = _closed_with_path_diagnostics(trade_records)
    out: dict[str, Any] = {
        "total": _path_summary_bucket(closed),
        "by_side": {
            "long": _path_summary_bucket([r for r in closed if r.get("direction") == "long"]),
            "short": _path_summary_bucket([r for r in closed if r.get("direction") == "short"]),
        },
        "by_exit_reason": {},
    }
    reasons = sorted({str(record.get("exit_reason") or "unknown") for record in closed})
    for reason in reasons:
        bucket = [record for record in closed if str(record.get("exit_reason") or "unknown") == reason]
        out["by_exit_reason"][reason] = _path_summary_bucket(bucket)

    optional_keys = (
        ("by_entry_profile", "entry_profile"),
        ("by_entry_context_state", "entry_context_state"),
        ("by_active_exit_profile", "active_exit_profile"),
    )
    for out_key, field in optional_keys:
        values = sorted(
            {
                str(record[field])
                for record in closed
                if record.get(field) is not None
            }
        )
        if values:
            out[out_key] = {
                value: _path_summary_bucket([record for record in closed if str(record.get(field)) == value])
                for value in values
            }
    return out


def _quality_bucket(records: list[dict[str, Any]]) -> dict[str, Any]:
    exit_reason_mix: dict[str, int] = {}
    for record in records:
        reason = str(record.get("exit_reason") or "unknown")
        exit_reason_mix[reason] = exit_reason_mix.get(reason, 0) + 1
    return {
        "trades": len(records),
        "avg_mfe_atr": _avg_non_null(records, "mfe_atr"),
        "avg_mfe_pct": _avg_non_null(records, "mfe_pct"),
        "avg_capture_ratio": _avg_non_null(records, "capture_ratio"),
        "avg_giveback_atr": _avg_non_null(records, "giveback_atr"),
        "avg_giveback_pct": _avg_non_null(records, "giveback_pct"),
        "exit_reason_mix": exit_reason_mix,
    }


def build_quality_flag_breakdown(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [record for record in trade_records if record.get("status") == "closed"]
    out: dict[str, Any] = {}
    for flag in QUALITY_FLAGS:
        bucket = [record for record in closed if flag in (record.get("quality_flags") or [])]
        if bucket:
            out[flag] = _quality_bucket(bucket)
    return out


def build_exit_component_quality_breakdown(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [
        record
        for record in trade_records
        if record.get("status") == "closed" and record.get("exit_component_id")
    ]
    components = sorted({str(record["exit_component_id"]) for record in closed})
    out: dict[str, Any] = {}
    for component in components:
        bucket = [record for record in closed if record.get("exit_component_id") == component]
        quality_flag_mix: dict[str, int] = {}
        for record in bucket:
            for flag in record.get("quality_flags") or []:
                quality_flag_mix[str(flag)] = quality_flag_mix.get(str(flag), 0) + 1
        out[component] = {
            "trades": len(bucket),
            "avg_mfe_atr": _avg_non_null(bucket, "mfe_atr"),
            "avg_mfe_pct": _avg_non_null(bucket, "mfe_pct"),
            "avg_capture_ratio": _avg_non_null(bucket, "capture_ratio"),
            "avg_giveback_atr": _avg_non_null(bucket, "giveback_atr"),
            "avg_giveback_pct": _avg_non_null(bucket, "giveback_pct"),
            "quality_flag_mix": quality_flag_mix,
            "signal_exit_winners": quality_flag_mix.get("signal_exit_winner", 0),
            "signal_exit_giveback_failures": quality_flag_mix.get("signal_exit_giveback_failure", 0),
        }
    return out
