"""Generic baseline vs managed paired-run comparison (Slice 9)."""

from __future__ import annotations

from typing import Any


def baseline_vs_managed_summary_placeholder() -> dict[str, Any]:
    """Empty comparison summary shape when no paired baseline run is available."""

    return {
        "saved_by_managed_stop": [],
        "hurt_by_managed_stop": [],
        "take_disabled_then_won": [],
        "take_disabled_then_lost": [],
        "runtime_exit_helped": [],
        "runtime_exit_hurt": [],
        "exit_layer_transition_matrix": {},
    }


def trade_pair_key(record: dict[str, Any]) -> str | None:
    """Stable pairing key for baseline/managed trades on the same entry signal."""

    direction = record.get("direction")
    if direction not in ("long", "short"):
        return None

    entry_idx = record.get("entry_idx")
    if isinstance(entry_idx, int) and entry_idx >= 0:
        return f"{direction}:{entry_idx}"

    entry_ms = record.get("entry_time_ms")
    if isinstance(entry_ms, int) and entry_ms > 0:
        return f"{direction}@{entry_ms}"

    trade_id = record.get("trade_id")
    if trade_id is not None:
        return f"{direction}:{trade_id}"
    return None


def _closed_trades_by_pair_key(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for record in trades:
        if record.get("status") != "closed":
            continue
        key = trade_pair_key(record)
        if key is None:
            continue
        out[key] = record
    return out


def exit_layer_for_record(record: dict[str, Any]) -> str:
    tm = record.get("trade_management")
    if isinstance(tm, dict):
        layer = tm.get("exit_layer")
        if isinstance(layer, str) and layer.strip():
            return layer.strip()

    layer = record.get("exit_layer")
    if isinstance(layer, str) and layer.strip():
        return layer.strip()

    exit_kind = record.get("exit_kind")
    if exit_kind in ("stop_loss", "take_profit", "signal"):
        return "exit_policy"

    exit_reason = record.get("exit_reason")
    if isinstance(exit_reason, str):
        if exit_reason.startswith("exit_management"):
            return "exit_management"
        prefix = exit_reason.split(":", 1)[0]
        if prefix in ("stop_loss", "take_profit", "signal"):
            return "exit_policy"

    return "unknown"


def _managed_exit_candidate_type(record: dict[str, Any]) -> str | None:
    tm = record.get("trade_management")
    if isinstance(tm, dict):
        candidate = tm.get("exit_candidate_type")
        if isinstance(candidate, str) and candidate:
            return candidate
    candidate = record.get("managed_exit_candidate_type")
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def _managed_exit_component_id(record: dict[str, Any]) -> str | None:
    tm = record.get("trade_management")
    if isinstance(tm, dict):
        component_id = tm.get("exit_component_id")
        if isinstance(component_id, str) and component_id:
            return component_id
    component_id = record.get("exit_component_id")
    if isinstance(component_id, str) and component_id:
        return component_id
    return None


def _active_take_at_exit(record: dict[str, Any]) -> str | None:
    tm = record.get("trade_management")
    if not isinstance(tm, dict):
        return None
    take_profile = tm.get("active_take_at_exit")
    if isinstance(take_profile, str) and take_profile:
        return take_profile
    return None


def _comparison_entry(
    *,
    pair_key: str,
    baseline: dict[str, Any],
    managed: dict[str, Any],
    pnl_delta: float,
    baseline_exit_layer: str,
    managed_exit_layer: str,
) -> dict[str, Any]:
    return {
        "pair_key": pair_key,
        "baseline_trade_id": baseline.get("trade_id"),
        "managed_trade_id": managed.get("trade_id"),
        "baseline_pnl": float(baseline.get("pnl") or 0.0),
        "managed_pnl": float(managed.get("pnl") or 0.0),
        "pnl_delta": pnl_delta,
        "baseline_exit_layer": baseline_exit_layer,
        "managed_exit_layer": managed_exit_layer,
        "managed_exit_candidate_type": _managed_exit_candidate_type(managed),
        "managed_exit_component_id": _managed_exit_component_id(managed),
        "active_take_at_exit": _active_take_at_exit(managed),
    }


def _is_managed_stop_close(managed: dict[str, Any], managed_exit_layer: str) -> bool:
    if managed_exit_layer != "exit_management":
        return False
    candidate = _managed_exit_candidate_type(managed)
    if candidate == "managed_stop":
        return True
    component_id = _managed_exit_component_id(managed)
    return component_id in ("break_even_stop", "lock_profit_stop")


def _is_runtime_exit_close(managed: dict[str, Any]) -> bool:
    if _managed_exit_candidate_type(managed) == "runtime_exit":
        return True
    return _managed_exit_component_id(managed) == "phase_runtime_exit"


def _take_disabled_at_exit(managed: dict[str, Any]) -> bool:
    take_profile = _active_take_at_exit(managed)
    return take_profile not in (None, "initial")


def build_baseline_vs_managed_summary(
    baseline_trades: list[dict[str, Any]],
    managed_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare paired closed trades and populate generic comparison categories."""

    baseline_by_key = _closed_trades_by_pair_key(baseline_trades)
    managed_by_key = _closed_trades_by_pair_key(managed_trades)

    saved_by_managed_stop: list[dict[str, Any]] = []
    hurt_by_managed_stop: list[dict[str, Any]] = []
    take_disabled_then_won: list[dict[str, Any]] = []
    take_disabled_then_lost: list[dict[str, Any]] = []
    runtime_exit_helped: list[dict[str, Any]] = []
    runtime_exit_hurt: list[dict[str, Any]] = []
    transition_matrix: dict[str, int] = {}

    for pair_key, managed in managed_by_key.items():
        baseline = baseline_by_key.get(pair_key)
        if baseline is None:
            continue

        baseline_pnl = float(baseline.get("pnl") or 0.0)
        managed_pnl = float(managed.get("pnl") or 0.0)
        pnl_delta = managed_pnl - baseline_pnl

        baseline_layer = exit_layer_for_record(baseline)
        managed_layer = exit_layer_for_record(managed)
        transition_key = f"{baseline_layer}->{managed_layer}"
        transition_matrix[transition_key] = transition_matrix.get(transition_key, 0) + 1

        entry = _comparison_entry(
            pair_key=pair_key,
            baseline=baseline,
            managed=managed,
            pnl_delta=pnl_delta,
            baseline_exit_layer=baseline_layer,
            managed_exit_layer=managed_layer,
        )

        if _is_managed_stop_close(managed, managed_layer):
            if pnl_delta > 0.0:
                saved_by_managed_stop.append(entry)
            elif pnl_delta < 0.0:
                hurt_by_managed_stop.append(entry)

        if _take_disabled_at_exit(managed):
            if pnl_delta > 0.0:
                take_disabled_then_won.append(entry)
            elif pnl_delta < 0.0:
                take_disabled_then_lost.append(entry)

        if _is_runtime_exit_close(managed):
            if pnl_delta > 0.0:
                runtime_exit_helped.append(entry)
            elif pnl_delta < 0.0:
                runtime_exit_hurt.append(entry)

    return {
        "saved_by_managed_stop": saved_by_managed_stop,
        "hurt_by_managed_stop": hurt_by_managed_stop,
        "take_disabled_then_won": take_disabled_then_won,
        "take_disabled_then_lost": take_disabled_then_lost,
        "runtime_exit_helped": runtime_exit_helped,
        "runtime_exit_hurt": runtime_exit_hurt,
        "exit_layer_transition_matrix": transition_matrix,
    }


def derive_break_even_stop_view(
    stop_management_breakdown: dict[str, Any] | None,
) -> dict[str, float | int]:
    """Derived BE view from generic stop_management_breakdown (not a report schema field)."""

    if not isinstance(stop_management_breakdown, dict):
        return {"trade_count": 0, "pnl": 0.0, "win_count": 0}
    entry = stop_management_breakdown.get("break_even_stop")
    if not isinstance(entry, dict):
        return {"trade_count": 0, "pnl": 0.0, "win_count": 0}
    return {
        "trade_count": int(entry.get("trade_count") or 0),
        "pnl": float(entry.get("pnl") or 0.0),
        "win_count": int(entry.get("win_count") or 0),
    }


def _resolve_variant(
    report: dict[str, Any],
    variant_name: str | None,
) -> dict[str, Any] | None:
    variants = report.get("variants")
    if not isinstance(variants, list) or not variants:
        return None
    if variant_name:
        for variant in variants:
            if isinstance(variant, dict) and variant.get("variant") == variant_name:
                return variant
        return None
    first = variants[0]
    return first if isinstance(first, dict) else None


def apply_baseline_vs_managed_comparison_to_report(
    managed_report: dict[str, Any],
    baseline_report: dict[str, Any],
    *,
    managed_variant: str | None = None,
    baseline_variant: str | None = None,
) -> dict[str, Any]:
    """Populate managed variant ``baseline_vs_managed_summary`` from paired reports."""

    managed_variant_payload = _resolve_variant(managed_report, managed_variant)
    baseline_variant_payload = _resolve_variant(baseline_report, baseline_variant)
    if managed_variant_payload is None or baseline_variant_payload is None:
        raise ValueError("Could not resolve managed or baseline variant in report payload")

    managed_trades = managed_variant_payload.get("trade_records")
    baseline_trades = baseline_variant_payload.get("trade_records")
    if not isinstance(managed_trades, list) or not isinstance(baseline_trades, list):
        raise ValueError("trade_records missing from one or both variants")

    summary = build_baseline_vs_managed_summary(baseline_trades, managed_trades)
    metrics = managed_variant_payload.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("managed variant metrics must be a dict")
    metrics["baseline_vs_managed_summary"] = summary
    return managed_report
