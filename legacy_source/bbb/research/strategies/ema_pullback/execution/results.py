"""Research run JSON artifacts: payload builder, trade normalization, writer.

Stage 9: structured machine-readable output under ``research/results/``.
"""

from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from data_engine.contracts import timeframe_ms

from research.strategies.ema_pullback.execution.exit_attribution import (
    ExitAttributionContext,
    classify_exit_attribution,
)
from research.strategies.ema_pullback.execution.trade_analyzer import (
    build_exit_component_quality_breakdown,
    build_path_diagnostics_summary,
    build_quality_flag_breakdown,
    build_trade_quality_diagnostics,
    path_diagnostics_config_payload,
    trade_quality_config_payload,
)

_PROFILE_KEYS = ("aligned", "countertrend", "neutral")
_CONTEXT_LABELS = frozenset({"up", "down", "neutral"})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_results_dir() -> Path:
    return _repo_root() / "research" / "results"


def build_run_id(
    utc: datetime,
    family: str,
    symbol: str,
    timeframe: str,
    *,
    suffix: str | None = None,
) -> str:
    """``<utc_timestamp>_<family>_<symbol>_<timeframe>[__<suffix>]`` (compact UTC, filesystem-safe)."""

    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    else:
        utc = utc.astimezone(timezone.utc)
    ts = utc.strftime("%Y-%m-%dT%H%M%SZ")
    sym = symbol.strip().upper()
    tf = timeframe.strip()
    base = f"{ts}_{family}_{sym}_{tf}"
    if suffix is None:
        return base
    return f"{base}__{sanitize_run_id_suffix(suffix)}"


def sanitize_run_id_suffix(suffix: str) -> str:
    """Normalize a programmatic run-id suffix to filesystem-safe characters."""

    import re

    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", suffix.strip())
    if not cleaned:
        raise ValueError("run_id_suffix must contain at least one safe character")
    return cleaned


def _format_created_at(utc: datetime) -> str:
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    else:
        utc = utc.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _scalar_json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int)):
        return value
    if hasattr(value, "item") and callable(value.item):
        try:
            return _scalar_json_safe(value.item())
        except Exception:  # pragma: no cover - defensive
            pass
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return int(ts.value // 1_000_000)
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return _scalar_json_safe(value.item())
    except ImportError:
        pass
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"unsupported scalar for JSON: {type(value)!r}")


def json_safe(value: Any) -> Any:
    """Recursively convert to JSON-friendly Python types (null for NaN/inf)."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    try:
        return _scalar_json_safe(value)
    except TypeError:
        return str(value)


def _series_index_aligned(series: pd.Series, index: pd.Index) -> bool:
    return series.index.equals(index)


def _attribution_context_aligned(ctx: ExitAttributionContext, index: pd.Index) -> bool:
    if not ctx.index.equals(index):
        return False
    for group in (
        ctx.long_signal_by_rule,
        ctx.short_signal_by_rule,
        ctx.distance_ratio_by_rule,
    ):
        for series in group:
            if series is not None and not _series_index_aligned(series, index):
                return False
    return _series_index_aligned(ctx.sl_stop_agg, index) and _series_index_aligned(ctx.tp_stop_agg, index)


def _can_use_exit_attribution(
    close: pd.Series,
    *,
    high: pd.Series | None,
    low: pd.Series | None,
    open_s: pd.Series | None,
    attribution: ExitAttributionContext | None,
) -> bool:
    if attribution is None or high is None or low is None or open_s is None:
        return False
    index = close.index
    if not (
        _series_index_aligned(high, index)
        and _series_index_aligned(low, index)
        and _series_index_aligned(open_s, index)
        and _attribution_context_aligned(attribution, index)
    ):
        return False
    return True


def _context_state_label(raw: Any) -> str:
    if isinstance(raw, str) and raw in _CONTEXT_LABELS:
        return raw
    return "unknown"


def _profile_label(raw: Any) -> str | None:
    if isinstance(raw, str) and raw in _PROFILE_KEYS:
        return raw
    return None


def _trade_fees_paid(row: dict[str, Any]) -> float:
    entry_fees = row.get("entry_fees")
    exit_fees = row.get("exit_fees")
    if entry_fees is not None or exit_fees is not None:
        return float(entry_fees or 0.0) + float(exit_fees or 0.0)
    fees = row.get("fees")
    if fees is not None:
        return float(fees)
    return 0.0


def _gross_return_pct(
    gross_pnl: float | None,
    entry_price: float | None,
    size: float | None,
) -> float | None:
    if gross_pnl is None or entry_price is None or size is None:
        return None
    notional = float(entry_price) * abs(float(size))
    if notional == 0.0:
        return None
    value = gross_pnl / notional
    return _scalar_json_safe(value)  # type: ignore[return-value]


def _closed_trades(trade_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in trade_records if record.get("status") == "closed"]


def _profit_factor_from_pnls(pnl_values: list[float]) -> float | None:
    gross_profit = sum(value for value in pnl_values if value > 0.0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0.0))
    if gross_loss == 0.0:
        return None
    return _scalar_json_safe(gross_profit / gross_loss)  # type: ignore[return-value]


def _avg_hold_bars(records: list[dict[str, Any]]) -> float | None:
    holds = [record["hold_bars"] for record in records if record.get("hold_bars") is not None]
    if not holds:
        return None
    return _scalar_json_safe(sum(holds) / len(holds))  # type: ignore[return-value]


def _bucket_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    trades = len(records)
    pnl_values = [float(record.get("pnl") or 0.0) for record in records]
    gross_pnl_values = [float(record.get("gross_pnl") or 0.0) for record in records]
    fees_values = [float(record.get("fees_paid") or 0.0) for record in records]
    returns = [float(record["return_pct"]) for record in records if record.get("return_pct") is not None]
    wins = sum(1 for value in pnl_values if value > 0.0)
    return {
        "trades": trades,
        "pnl": _scalar_json_safe(sum(pnl_values)),
        "gross_pnl": _scalar_json_safe(sum(gross_pnl_values)),
        "fees_paid": _scalar_json_safe(sum(fees_values)),
        "profit_factor": _profit_factor_from_pnls(pnl_values),
        "win_rate": _scalar_json_safe(wins / trades) if trades else None,
        "avg_return_pct": _scalar_json_safe(sum(returns) / len(returns)) if returns else None,
        "avg_hold_bars": _avg_hold_bars(records),
    }


def _profile_bucket_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = _bucket_metrics(records)
    mix: dict[str, int] = {}
    for record in records:
        reason = str(record.get("exit_reason") or "unknown")
        mix[reason] = mix.get(reason, 0) + 1
    metrics["exit_reason_mix"] = mix
    return metrics


def build_profile_breakdown(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate closed trades by ``entry_profile``."""

    closed = _closed_trades(trade_records)
    return {
        profile: _profile_bucket_metrics(
            [record for record in closed if record.get("entry_profile") == profile]
        )
        for profile in _PROFILE_KEYS
    }


def build_profile_side_breakdown(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate closed trades by direction and ``entry_profile`` (side × context)."""

    closed = _closed_trades(trade_records)
    out: dict[str, Any] = {}
    for side in ("long", "short"):
        side_closed = [record for record in closed if record.get("direction") == side]
        section: dict[str, Any] = {
            profile: _profile_bucket_metrics(
                [record for record in side_closed if record.get("entry_profile") == profile]
            )
            for profile in _PROFILE_KEYS
        }
        section["total"] = _profile_bucket_metrics(side_closed)
        out[side] = section
    total_section: dict[str, Any] = {
        profile: _profile_bucket_metrics(
            [record for record in closed if record.get("entry_profile") == profile]
        )
        for profile in _PROFILE_KEYS
    }
    total_section["total"] = _profile_bucket_metrics(closed)
    out["total"] = total_section
    return out


def build_exit_reason_breakdown(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate closed trades by full ``exit_reason`` string."""

    closed = _closed_trades(trade_records)
    reasons = sorted({str(record.get("exit_reason") or "unknown") for record in closed})
    return {reason: _bucket_metrics([r for r in closed if str(r.get("exit_reason") or "unknown") == reason]) for reason in reasons}


def build_bounce_counter_breakdown(trade_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate closed trades by side and entry effective bounce number."""

    closed = [
        record
        for record in _closed_trades(trade_records)
        if record.get("entry_effective_bounce_number") is not None
    ]
    if not closed:
        return None
    out: dict[str, Any] = {}
    for side in ("long", "short"):
        side_records = [record for record in closed if record.get("entry_bounce_counter_side") == side]
        bounce_numbers = sorted(
            {
                int(record["entry_effective_bounce_number"])
                for record in side_records
                if record.get("entry_effective_bounce_number") is not None
            }
        )
        out[side] = {
            str(number): _bucket_metrics(
                [
                    record
                    for record in side_records
                    if int(record.get("entry_effective_bounce_number") or -1) == number
                ]
            )
            for number in bounce_numbers
        }
        out[side]["total"] = _bucket_metrics(side_records)
    out["total"] = _bucket_metrics(closed)
    return out


def build_trade_quality_breakdowns(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "quality_flag_breakdown": build_quality_flag_breakdown(trade_records),
        "exit_component_quality_breakdown": build_exit_component_quality_breakdown(trade_records),
        "path_diagnostics_summary": build_path_diagnostics_summary(trade_records),
    }


def build_fee_diagnostics(
    trade_records: list[dict[str, Any]],
    *,
    fees_rate: float,
) -> dict[str, Any]:
    closed = _closed_trades(trade_records)
    total_fees = sum(float(record.get("fees_paid") or 0.0) for record in closed)
    gross_pnl = sum(float(record.get("gross_pnl") or 0.0) for record in closed)
    net_pnl = sum(float(record.get("pnl") or 0.0) for record in closed)
    gross_profit = sum(float(record.get("gross_pnl") or 0.0) for record in closed if float(record.get("gross_pnl") or 0.0) > 0.0)
    out: dict[str, Any] = {
        "total_fees_paid": _scalar_json_safe(total_fees),
        "gross_pnl": _scalar_json_safe(gross_pnl),
        "net_pnl": _scalar_json_safe(net_pnl),
        "fees_rate": _scalar_json_safe(fees_rate),
    }
    if gross_profit > 0.0:
        out["fees_as_pct_of_gross_profit"] = _scalar_json_safe(total_fees / gross_profit)
    else:
        out["fees_as_pct_of_gross_profit"] = None
    return out


def _index_to_open_time_ms(index: pd.Index, idx: Any) -> int | None:
    if idx is None or (isinstance(idx, float) and math.isnan(idx)):
        return None
    try:
        ii = int(idx)
    except (TypeError, ValueError):
        return None
    if ii < 0 or ii >= len(index):
        return None
    ts = index[ii]
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return int(ts.value // 1_000_000)


def extract_trade_records(
    pf: Any,
    close: pd.Series,
    *,
    high: pd.Series | None = None,
    low: pd.Series | None = None,
    open_s: pd.Series | None = None,
    attribution: ExitAttributionContext | None = None,
    profile_long: pd.Series | None = None,
    profile_short: pd.Series | None = None,
    context_state: pd.Series | None = None,
    diagnostic_atr_series: pd.Series | None = None,
    base_timeframe: str | None = None,
    exit_component_map: dict[str, str] | None = None,
    strategy_spec: Any | None = None,
    context_bundle: Any | None = None,
    setup_traces_by_instance_side: dict[str, dict[str, dict[str, pd.Series]]] | None = None,
) -> list[dict[str, Any]]:
    """Normalize vectorbt portfolio trades into Stage 9 trade_records (library-agnostic fields)."""

    index = close.index
    records_df = pf.trades.records
    if records_df is None or len(records_df) == 0:
        return []

    use_attr = _can_use_exit_attribution(
        close, high=high, low=low, open_s=open_s, attribution=attribution
    )
    base_timeframe_minutes: int | None = None
    if base_timeframe is not None:
        base_timeframe_minutes = timeframe_ms(base_timeframe.strip()) // 60_000

    out: list[dict[str, Any]] = []
    # TradeDirectionT(Long=0, Short=1), TradeStatusT(Open=0, Closed=1)
    for i, row in enumerate(records_df.to_dict("records")):
        direction_code = int(row.get("direction", 0))
        status_code = int(row.get("status", 0))
        direction = "long" if direction_code == 0 else "short"
        status = "open" if status_code == 0 else "closed"

        entry_ms = _index_to_open_time_ms(index, row.get("entry_idx"))
        exit_ms = _index_to_open_time_ms(index, row.get("exit_idx"))

        entry_p = _scalar_json_safe(row.get("entry_price"))
        exit_p = _scalar_json_safe(row.get("exit_price"))
        size_v = _scalar_json_safe(row.get("size"))
        pnl_v = _scalar_json_safe(row.get("pnl"))
        ret_v = _scalar_json_safe(row.get("return"))

        if status == "open":
            exit_ms = None
            exit_p = None

        exit_attr = None
        if status == "open":
            exit_reason = "open"
        elif use_attr:
            assert attribution is not None and high is not None and low is not None and open_s is not None
            exit_attr = classify_exit_attribution(
                row=row,
                close=close,
                high=high,
                low=low,
                open_=open_s,
                ctx=attribution,
                component_map=exit_component_map,
            )
            exit_reason = exit_attr.exit_reason
        else:
            exit_reason = "unknown"

        record: dict[str, Any] = {
            "trade_id": i + 1,
            "direction": direction,
            "status": status,
            "entry_time_ms": entry_ms,
            "exit_time_ms": exit_ms,
            "entry_price": entry_p,
            "exit_price": exit_p,
            "size": size_v,
            "pnl": pnl_v,
            "return_pct": ret_v,
            "exit_reason": exit_reason,
        }

        if status == "closed":
            fees_paid = _scalar_json_safe(_trade_fees_paid(row))
            pnl_f = float(pnl_v) if pnl_v is not None else 0.0
            fees_f = float(fees_paid) if fees_paid is not None else 0.0
            gross_pnl = _scalar_json_safe(pnl_f + fees_f)
            record["gross_pnl"] = gross_pnl
            record["fees_paid"] = fees_paid
            record["gross_return_pct"] = _gross_return_pct(
                float(gross_pnl) if gross_pnl is not None else None,
                float(entry_p) if entry_p is not None else None,
                float(size_v) if size_v is not None else None,
            )

            if exit_attr is not None:
                record["exit_group"] = exit_attr.exit_group
                record["exit_profile"] = exit_attr.exit_profile
                record["exit_component_id"] = exit_attr.exit_component_id
                record["exit_instance_id"] = exit_attr.exit_instance_id
                record["exit_kind"] = exit_attr.exit_kind
            else:
                record["exit_group"] = None
                record["exit_profile"] = None
                record["exit_component_id"] = None
                record["exit_instance_id"] = None
                record["exit_kind"] = None

            try:
                entry_idx = int(row.get("entry_idx"))
                exit_idx = int(row.get("exit_idx"))
            except (TypeError, ValueError):
                entry_idx = -1
                exit_idx = -1
            if entry_idx >= 0:
                record["entry_idx"] = entry_idx
            if exit_idx >= 0:
                record["exit_idx"] = exit_idx
            if entry_idx >= 0 and exit_idx >= 0:
                hold_bars = exit_idx - entry_idx + 1
                record["hold_bars"] = hold_bars
                if base_timeframe_minutes is not None:
                    record["hold_minutes"] = hold_bars * base_timeframe_minutes

            entry_profile: str | None = None
            if direction == "long" and profile_long is not None and 0 <= entry_idx < len(profile_long):
                entry_profile = _profile_label(profile_long.iloc[entry_idx])
            elif direction == "short" and profile_short is not None and 0 <= entry_idx < len(profile_short):
                entry_profile = _profile_label(profile_short.iloc[entry_idx])
            if entry_profile is not None:
                record["entry_profile"] = entry_profile
                record["active_exit_profile"] = entry_profile

            if context_state is not None and 0 <= entry_idx < len(context_state):
                record["entry_context_state"] = _context_state_label(context_state.iloc[entry_idx])

            if setup_traces_by_instance_side is not None and 0 <= entry_idx < len(index):
                entry_setup_diagnostics: dict[str, dict[str, Any]] = {}
                for instance_id, by_side in setup_traces_by_instance_side.items():
                    setup_trace = by_side.get(direction)
                    if setup_trace is None:
                        continue
                    entry_setup_diagnostics[instance_id] = {
                        "trend_episode_id": _scalar_json_safe(
                            setup_trace["trend_episode_id"].iloc[entry_idx]
                        ),
                        "effective_bounce_number": _scalar_json_safe(
                            setup_trace["effective_bounce_number"].iloc[entry_idx]
                        ),
                        "completed_bounce_count": _scalar_json_safe(
                            setup_trace["completed_bounce_count"].iloc[entry_idx]
                        ),
                        "side": direction,
                    }
                if entry_setup_diagnostics:
                    record["entry_setup_diagnostics"] = entry_setup_diagnostics

            if strategy_spec is not None:
                from research.strategies.ema_pullback.context.consumption_trace import (
                    consumption_attribution_for_trade,
                )

                entry_cc, exit_cc = consumption_attribution_for_trade(
                    strategy_spec,
                    entry_idx=entry_idx,
                    direction=direction,
                    context_bundle=context_bundle,
                    index=index,
                )
                if entry_cc is not None:
                    record["entry_context_consumption"] = entry_cc
                if exit_cc is not None:
                    record["exit_context_consumption"] = exit_cc

            if (
                high is not None
                and low is not None
                and entry_p is not None
                and exit_p is not None
                and entry_idx >= 0
                and exit_idx >= entry_idx
            ):
                record.update(
                    build_trade_quality_diagnostics(
                        record,
                        entry_idx=entry_idx,
                        exit_idx=exit_idx,
                        high=high,
                        low=low,
                        index=index,
                        open_=open_s,
                        close=close,
                        attribution=attribution,
                        diagnostic_atr_series=diagnostic_atr_series,
                    )
                )

        out.append(record)
    return out


def build_execution_integrated_trade_records(
    closed_trades: list[dict[str, Any]],
    *,
    index: pd.Index,
    fees_rate: float = 0.0,
    base_timeframe: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize execution-integrated managed closes into trade_records shape."""

    base_timeframe_minutes: int | None = None
    if base_timeframe is not None:
        base_timeframe_minutes = timeframe_ms(base_timeframe.strip()) // 60_000

    out: list[dict[str, Any]] = []
    for i, item in enumerate(closed_trades):
        entry_idx = int(item["entry_idx"])
        exit_idx = int(item["exit_idx"])
        entry_p = float(item["entry_price"])
        direction = item["direction"]
        is_open = bool(item.get("open", False))
        status = "open" if is_open else "closed"
        exit_p = float(item["exit_price"]) if status == "closed" else None

        if direction == "long":
            gross_pnl = (exit_p - entry_p) if exit_p is not None else None
        else:
            gross_pnl = (entry_p - exit_p) if exit_p is not None else None

        fees_paid = 0.0
        if gross_pnl is not None and fees_rate:
            assert exit_p is not None
            fees_paid = abs(entry_p + exit_p) * fees_rate
        pnl = (gross_pnl - fees_paid) if gross_pnl is not None else None
        ret_pct = (pnl / entry_p) if pnl is not None and entry_p else None

        entry_ms = _index_to_open_time_ms(index, entry_idx)
        exit_ms = _index_to_open_time_ms(index, exit_idx) if status == "closed" else None

        exit_attr = item.get("exit_attribution")
        if is_open:
            exit_reason = "open"
        elif exit_attr is not None:
            exit_reason = exit_attr.exit_reason
        else:
            exit_reason = "unknown"

        record: dict[str, Any] = {
            "trade_id": item.get("trade_id", i + 1),
            "direction": direction,
            "status": status,
            "entry_time_ms": entry_ms,
            "exit_time_ms": exit_ms,
            "entry_price": entry_p,
            "exit_price": exit_p,
            "size": 1.0,
            "pnl": pnl,
            "return_pct": ret_pct,
            "exit_reason": exit_reason,
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
        }

        if status == "closed" and exit_attr is not None:
            record["exit_group"] = exit_attr.exit_group
            record["exit_profile"] = exit_attr.exit_profile
            record["exit_component_id"] = exit_attr.exit_component_id
            record["exit_instance_id"] = exit_attr.exit_instance_id
            record["exit_kind"] = exit_attr.exit_kind

        exit_layer = item.get("exit_layer")
        if status == "closed" and isinstance(exit_layer, str):
            record["exit_layer"] = exit_layer

        winner = item.get("winner")
        if status == "closed" and winner is not None and getattr(winner, "candidate_type", None):
            record["managed_exit_candidate_type"] = winner.candidate_type

        if status == "closed" and gross_pnl is not None:
            record["gross_pnl"] = gross_pnl
            record["fees_paid"] = fees_paid
            record["gross_return_pct"] = ret_pct

        entry_profile = item.get("locked_profile", "neutral")
        record["entry_profile"] = entry_profile
        record["active_exit_profile"] = entry_profile

        hold_bars = exit_idx - entry_idx + 1
        record["hold_bars"] = hold_bars
        if base_timeframe_minutes is not None:
            record["hold_minutes"] = hold_bars * base_timeframe_minutes

        out.append(record)
    return out


_MANAGED_EXIT_CANDIDATE_BREAKDOWN: dict[str, str] = {
    "managed_stop": "stop_management_breakdown",
    "runtime_exit": "runtime_exit_breakdown",
}


def _empty_managed_breakdown_entry() -> dict[str, Any]:
    return {"trade_count": 0, "pnl": 0.0, "win_count": 0}


def _accumulate_managed_breakdown(
    bucket: dict[str, Any],
    component_key: str,
    record: dict[str, Any],
) -> None:
    entry = bucket.setdefault(component_key, _empty_managed_breakdown_entry())
    entry["trade_count"] = int(entry["trade_count"]) + 1
    pnl = float(record.get("pnl") or 0.0)
    entry["pnl"] = float(entry.get("pnl") or 0.0) + pnl
    if pnl > 0.0:
        entry["win_count"] = int(entry.get("win_count") or 0) + 1


def build_managed_layer_breakdowns(
    trade_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Generic managed layer breakdowns keyed by component_id."""

    stop_breakdown: dict[str, Any] = {}
    take_breakdown: dict[str, Any] = {}
    runtime_breakdown: dict[str, Any] = {}
    for record in trade_records:
        if record.get("status") != "closed":
            continue
        tm = record.get("trade_management")
        if not isinstance(tm, dict):
            continue

        layer = tm.get("exit_layer")
        component_id = tm.get("exit_component_id")
        candidate_type = tm.get("exit_candidate_type") or record.get(
            "managed_exit_candidate_type"
        )
        if layer == "exit_management.stop_rule" and isinstance(component_id, str) and component_id:
            _accumulate_managed_breakdown(stop_breakdown, component_id, record)
        elif layer == "exit_management.runtime_exit" and isinstance(
            component_id, str
        ) and component_id:
            _accumulate_managed_breakdown(runtime_breakdown, component_id, record)
        elif layer == "exit_management" and isinstance(component_id, str) and component_id:
            breakdown_key = _MANAGED_EXIT_CANDIDATE_BREAKDOWN.get(str(candidate_type or ""))
            if breakdown_key == "stop_management_breakdown":
                _accumulate_managed_breakdown(stop_breakdown, component_id, record)
            elif breakdown_key == "runtime_exit_breakdown":
                _accumulate_managed_breakdown(runtime_breakdown, component_id, record)

        take_component_id = tm.get("active_take_component_id")
        take_profile = tm.get("active_take_at_exit")
        if isinstance(take_component_id, str) and take_component_id and take_profile not in (
            None,
            "initial",
        ):
            _accumulate_managed_breakdown(take_breakdown, take_component_id, record)

    return {
        "stop_management_breakdown": stop_breakdown,
        "take_management_breakdown": take_breakdown,
        "runtime_exit_breakdown": runtime_breakdown,
    }


def baseline_vs_managed_summary_placeholder() -> dict[str, Any]:
    """Empty comparison summary shape when no paired baseline run is available."""

    from research.strategies.ema_pullback.execution.managed_comparison import (
        baseline_vs_managed_summary_placeholder as _placeholder,
    )

    return _placeholder()


def build_research_run_payload(
    *,
    run_id: str,
    created_at: datetime,
    family: str,
    symbol: str,
    timeframe: str,
    candles_count: int,
    data_range_from_ms: int,
    data_range_to_ms: int,
    variants: list[dict[str, Any]],
    batch_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble top-level artifact dict (field order stable for readability)."""

    payload = {
        "run_id": run_id,
        "created_at": _format_created_at(created_at),
        "report_schema_version": 6,
        "family": family,
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe.strip(),
        "candles": int(candles_count),
        "data_range": {
            "from_open_time_ms": int(data_range_from_ms),
            "to_open_time_ms": int(data_range_to_ms),
        },
        "variants_count": len(variants),
        "trade_quality_config": trade_quality_config_payload(),
        "path_diagnostics_config": path_diagnostics_config_payload(),
        "variants": variants,
    }
    if batch_metadata is not None:
        payload["batch_metadata"] = batch_metadata
    return payload


SUMMARY_SCHEMA_VERSION = 1

_STRIP_VARIANT_KEYS = frozenset(
    {
        "trade_records",
        "trades",
        "candles",
        "ohlcv",
        "component_events",
        "trade_management_events",
        "signal_trace",
        "trace",
    }
)

_STRIP_TOP_LEVEL_KEYS = frozenset(
    {
        "candles",
        "ohlcv",
        "component_events",
        "signal_trace",
        "trace",
        "trade_records",
        "trades",
    }
)


def run_report_relpath(run_id: str) -> str:
    return f"research/results/runs/{run_id}.json"


def run_summary_report_relpath(run_id: str) -> str:
    return f"research/results/runs/{run_id}.summary.json"


def _trade_record_counts(trade_records: list[dict[str, Any]]) -> dict[str, int]:
    closed = sum(1 for record in trade_records if record.get("status") == "closed")
    open_count = sum(1 for record in trade_records if record.get("status") == "open")
    return {
        "trade_records_count": len(trade_records),
        "closed_trades_count": closed,
        "open_trades_count": open_count,
    }


def build_compact_report_payload(
    full_report: Mapping[str, Any],
    *,
    source_report_path: str | None = None,
) -> dict[str, Any]:
    """Projection of a full run report without per-trade heavy arrays."""

    run_id = str(full_report["run_id"])
    if source_report_path is None:
        source_report_path = run_report_relpath(run_id)

    stripped = copy.deepcopy(dict(full_report))
    for key in _STRIP_TOP_LEVEL_KEYS:
        stripped.pop(key, None)

    variants = stripped.get("variants")
    if isinstance(variants, list):
        compact_variants: list[Any] = []
        for variant in variants:
            if not isinstance(variant, dict):
                compact_variants.append(variant)
                continue
            compact_variant = {
                key: value for key, value in variant.items() if key not in _STRIP_VARIANT_KEYS
            }
            trade_records = variant.get("trade_records")
            if isinstance(trade_records, list):
                compact_variant.update(_trade_record_counts(trade_records))
            compact_variants.append(compact_variant)
        stripped["variants"] = compact_variants

    return {
        **stripped,
        "artifact_kind": "run_summary",
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "source_report_path": source_report_path,
    }


def write_research_results(
    payload: dict[str, Any],
    *,
    results_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Write full report, compact summary, and ``latest.json``; return all three paths."""

    base = results_dir if results_dir is not None else default_results_dir()
    runs = base / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    run_id = str(payload["run_id"])
    safe = json_safe(payload)
    text = json.dumps(safe, indent=2, ensure_ascii=False)

    run_path = runs / f"{run_id}.json"
    summary_path = runs / f"{run_id}.summary.json"
    latest_path = base / "latest.json"
    run_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")

    summary_payload = build_compact_report_payload(
        payload,
        source_report_path=run_report_relpath(run_id),
    )
    summary_text = json.dumps(json_safe(summary_payload), indent=2, ensure_ascii=False)
    summary_path.write_text(summary_text, encoding="utf-8")
    return latest_path, run_path, summary_path
